from shared.cache.redis_client import CacheClient,SessionStore
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings

from app.schemas.chat_query import ChatQueryResponse,SourceChunk
from app.services.llm_client import GeminiClient,prompt_cache_key


RESPONSE_CACHE_TTL_SECONDS=3600
SESSION_TTL_SECONDS=60 * 60 * 24
SESSION_DOCS_KEY_PREFIX="docs:"

class RAGService:
    def __init__(self):
        self._worker_client=ServiceClient(base_url=settings.AI_WORKER_SERVICE_URL)
        self._llm_client=GeminiClient()
        self._cache=CacheClient()
        self._sessions=SessionStore()
    async def aclose(self) -> None:
        await self._worker_client.aclose()
        await self._llm_client.aclose()

    async def _search_and_build_context(self,question:str,top_k:int,owner_id:str,document_ids:list[str] | None) -> tuple[list[SourceChunk],str]:
        # owner_id comes from the caller's verified JWT (see chat_query_route.py),
        # never from client-supplied input, and is always sent to the worker so
        # a request can never retrieve another user's document chunks -
        # regardless of what document_ids the client asks for.
        search_response= await self._worker_client.post(
            "/api/v1/internal/search/",
            json={"query":question,"top_k":top_k,"document_ids":document_ids,"owner_id":owner_id}
        )
        results=search_response.json()["results"]
        sources=[SourceChunk(**r) for r in results]
        context="\n\n".join(f"[{s.document_id}#{s.chunk_index}]{s.text}" for s in sources)
        return sources,context

    async def set_session_documents(self,owner_id:str,session_id:str,document_ids:list[str]) -> list[str]:
        """
        Persists the multi-document scope for a session (owner isolation
        is still enforced downstream in FaissStore.search - this list only
        narrows within a user's own documents, never widens beyond it).
        Keyed by (owner_id, session_id) together, not session_id alone -
        session_id is client-generated and not a secret (it's stored in
        the frontend's localStorage), so without the owner_id in the key
        anyone who learned or guessed another user's session_id could read
        or overwrite their session's document scope. Same reasoning
        applies to _append_history below.
        """
        await self._sessions.set(self._docs_key(owner_id,session_id),document_ids,ttl_seconds=SESSION_TTL_SECONDS)
        return document_ids

    async def get_session_documents(self,owner_id:str,session_id:str) -> list[str] | None:
        return await self._sessions.get(self._docs_key(owner_id,session_id))

    @staticmethod
    def _docs_key(owner_id:str,session_id:str) -> str:
        return f"{SESSION_DOCS_KEY_PREFIX}{owner_id}:{session_id}"

    @staticmethod
    def _history_key(owner_id:str,session_id:str) -> str:
        return f"{owner_id}:{session_id}"

    async def _resolve_document_scope(self,owner_id:str,session_id:str,document_ids:list[str] | None) -> list[str] | None:
        """Explicit per-request document_ids always win; otherwise fall
        back to whatever scope was set for this session via
        set_session_documents(), if any. Returning None means "search
        across all of the caller's documents", same as before this feature
        existed - a session with no configured scope is unaffected."""
        if document_ids is not None:
            return document_ids
        return await self.get_session_documents(owner_id,session_id)

    async def answer(self,session_id:str,question:str,top_k:int,owner_id:str,document_ids:list[str] | None=None) -> ChatQueryResponse:
        document_ids=await self._resolve_document_scope(owner_id,session_id,document_ids)
        sources,context=await self._search_and_build_context(question,top_k,owner_id,document_ids)

        # owner_id is salted into the cache key (via the question string) so
        # two different users asking the identical question never share a
        # cached answer/context. This keeps prompt_cache_key()'s signature in
        # llm_client.py untouched.
        cache_key=prompt_cache_key(f"{owner_id}:{question}",context)
        cached_answer=await self._cache.get(cache_key)
        if cached_answer is not None:
            await self._append_history(owner_id,session_id,question,cached_answer)
            return ChatQueryResponse(answer=cached_answer,sources=sources,cached=True)
        prompt=self._build_prompt(question,context)
        answer= await self._llm_client.generate(prompt)

        await self._cache.set(cache_key,answer,ttl_seconds=RESPONSE_CACHE_TTL_SECONDS)
        await self._append_history(owner_id,session_id,question,answer)

        return ChatQueryResponse(answer=answer,sources=sources,cached=False)

    async def answer_stream(self,session_id:str,question:str,top_k:int,owner_id:str,document_ids:list[str] | None=None):
        """
        Async generator yielding transport-agnostic event dicts:
          {"type": "sources", "sources": [...]}   - once, up front
          {"type": "delta", "text": "..."}         - zero or more times
          {"type": "done", "cached": bool}          - once, at the end

        Deliberately has no idea what SSE framing looks like - that's the
        route layer's job (see chat_query_route.py). Same cache-key and
        session-history side effects as answer(), just applied after the
        full answer has been assembled from the streamed deltas rather than
        all at once.
        """
        document_ids=await self._resolve_document_scope(owner_id,session_id,document_ids)
        sources,context=await self._search_and_build_context(question,top_k,owner_id,document_ids)
        yield {"type":"sources","sources":[s.model_dump() for s in sources]}

        cache_key=prompt_cache_key(f"{owner_id}:{question}",context)
        cached_answer=await self._cache.get(cache_key)
        if cached_answer is not None:
            await self._append_history(owner_id,session_id,question,cached_answer)
            yield {"type":"delta","text":cached_answer}
            yield {"type":"done","cached":True}
            return

        prompt=self._build_prompt(question,context)
        parts:list[str]=[]
        async for delta in self._llm_client.generate_stream(prompt):
            parts.append(delta)
            yield {"type":"delta","text":delta}
        full_answer="".join(parts)

        await self._cache.set(cache_key,full_answer,ttl_seconds=RESPONSE_CACHE_TTL_SECONDS)
        await self._append_history(owner_id,session_id,question,full_answer)
        yield {"type":"done","cached":False}

    async def _append_history(self,owner_id:str,session_id:str,question:str,answer:str) -> None:
        key=self._history_key(owner_id,session_id)
        history=await self._sessions.get(key) or []
        history.append({"question":question,"answer":answer})
        await self._sessions.set(key,history,ttl_seconds=SESSION_TTL_SECONDS)

    async def get_history(self,owner_id:str,session_id:str) -> list[dict]:
        """
        Reads back what _append_history() above has been writing all
        along - answer()/answer_stream() already persist every turn to
        Redis (keyed by owner_id+session_id, same isolation reasoning as
        _docs_key), but until now nothing ever read it back out. Returns
        an empty list for a session with no history yet (new session, or
        one that expired after SESSION_TTL_SECONDS of inactivity) rather
        than raising - "no history" is a normal, expected state.
        """
        return await self._sessions.get(self._history_key(owner_id,session_id)) or []

    @staticmethod
    def _build_prompt(question:str,context:str) -> str:
        return(
            "Answer the question using only the context below."
            "If the answer isn't in the context, say you don't know.\n\n"
            f"Context:\n{context}\n\nQuestion: {question}"
        )