from shared.cache.redis_client import CacheClient,SessionStore
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings

from app.schemas.chat_query import ChatQueryResponse,SourceChunk
from app.services.llm_client import GeminiClient,prompt_cache_key


RESPONSE_CACHE_TTL_SECONDS=3600
SESSION_TTL_SECONDS=60 * 60 * 24

class RAGService:
    def __init__(self):
        self._worker_client=ServiceClient(base_url=settings.AI_WORKER_SERVICE_URL)
        self._llm_client=GeminiClient()
        self._cache=CacheClient()
        self._sessions=SessionStore()
    async def aclose(self) -> None:
        await self._worker_client.aclose()
        await self._llm_client.aclose()

    async def answer(self,session_id:str,question:str,top_k:int,owner_id:str,document_ids:list[str] | None=None) -> ChatQueryResponse:
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

        # owner_id is salted into the cache key (via the question string) so
        # two different users asking the identical question never share a
        # cached answer/context. This keeps prompt_cache_key()'s signature in
        # llm_client.py untouched.
        cache_key=prompt_cache_key(f"{owner_id}:{question}",context)
        cached_answer=await self._cache.get(cache_key)
        if cached_answer is not None:
            await self._append_history(session_id,question,cached_answer)
            return ChatQueryResponse(answer=cached_answer,sources=sources,cached=True)
        prompt=self._build_prompt(question,context)
        answer= await self._llm_client.generate(prompt)

        await self._cache.set(cache_key,answer,ttl_seconds=RESPONSE_CACHE_TTL_SECONDS)
        await self._append_history(session_id,question,answer)

        return ChatQueryResponse(answer=answer,sources=sources,cached=False)

    async def _append_history(self,session_id:str,question:str,answer:str) -> None:
        history=await self._sessions.get(session_id) or []
        history.append({"question":question,"answer":answer})
        await self._sessions.set(session_id,history,ttl_seconds=SESSION_TTL_SECONDS)

    @staticmethod
    def _build_prompt(question:str,context:str) -> str:
        return(
            "Answer the question using only the context below."
            "If the answer isn't in the context, say you don't know.\n\n"
            f"Context:\n{context}\n\nQuestion: {question}"
        )