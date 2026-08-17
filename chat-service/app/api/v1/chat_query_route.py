import json
from fastapi import APIRouter,Request
from fastapi.responses import StreamingResponse

from shared.exceptions.exceptions import AppException
from shared.logger.logger import get_logger

from app.api.deps import CurrentUserDep
from app.schemas.chat_query import (
    ChatHistoryResponse,
    ChatQueryRequest,
    ChatQueryResponse,
    SessionDocumentRequest,
    SessionDocumentResponse,
)

logger=get_logger(__name__)
router = APIRouter()

@router.put("/sessions/{session_id}/documents",response_model=SessionDocumentResponse)
async def set_session_documents(session_id:str,body:SessionDocumentRequest,request:Request,current_user:CurrentUserDep):
    """
    Scopes a chat session to a fixed set of a documents so document_ids
    doesn't need to be repeated on every /query or /query/stream call.
    Ownership isn't re-checked here (FaissStore.search always filters by
    the caller's owner_id downstream regardless of what's in this list -
    see rag_service.py), so scoping to a document you don't own just 
    means that document silently never matches, nothing is leaked.
    """
    rag_service=request.app.state.rag_service
    document_ids = await rag_service.set_session_documents(str(current_user.id),session_id,body.document_ids)
    return SessionDocumentResponse(session_id=session_id,document_ids=document_ids)

@router.get("/sessions/{session_id}/documents",response_model=SessionDocumentResponse)
async def get_session_documents(session_id:str,request:Request,current_user:CurrentUserDep):
    rag_service = request.app.state.rag_service
    document_ids=await rag_service.get_session_documents(str(current_user.id),session_id) or []
    return SessionDocumentResponse(session_id=session_id,document_ids=document_ids)
@router.get("/sessions/{session_id}/history",response_model=ChatHistoryResponse)
async def get_chat_history(session_id:str,request:Request,current_user:CurrentUserDep):
    """
    Returns every question/answer turn recorded for this session so far
    (see RAGService._append_history, called from both answer() and
    answer_stream()). Keyed by (owner_id, session_id) the same way
    set_session_documents()/get_session_documents() above are - a session_id
    alone isn't a secret (it's client-generated and lives in localStorage),
    so history is only ever readable by the user who owns it, scoped by
    their verified JWT, never by session_id alone.
    """
    rag_service=request.app.state.rag_service
    history=await rag_service.get_history(str(current_user.id),session_id)
    return ChatHistoryResponse(session_id=session_id,history=history)

@router.post("/query",response_model=ChatQueryResponse)
async def query(request:Request,current_user:CurrentUserDep,body:ChatQueryRequest):
    rag_service=request.app.state.rag_service
    return await rag_service.answer(body.session_id,body.question,body.top_k,str(current_user.id),body.document_ids)

@router.post("/query/stream")
async def query_stream(request:Request,current_user:CurrentUserDep,body:ChatQueryRequest):
    rag_service=request.app.state.rag_service

    async def event_source():
        # Deliberately catches errors HERE rather than letting them
        # propagate to the app-wide AppException handler (shared/exceptions/
        # handlers.py). By the time rag_service.answer_stream() raises
        # (e.g. LLMError/LLMRateLimitedError from a Gemini failure, always
        # AFTER the "sources" event has already been yielded and the
        # streaming response has already committed its 200 OK + chunked
        # headers to the client), that global handler can no longer send a
        # fresh JSONResponse - Starlette itself raises
        # RuntimeError("Caught handled exception, but response already
        # started.") when it tries, and the client just sees the
        # connection die mid-chunk with no explanation
        # (httpx.RemoteProtocolError / "incomplete chunked read" on
        # whatever's consuming this, including the gateway's own SSE relay
        # in proxy.py). Catching it here instead lets us emit one last
        # well-formed SSE event describing what went wrong, then end the
        # generator cleanly so StreamingResponse can close the chunked
        # body properly instead of the connection just dying.
        try:
            async for event in rag_service.answer_stream(
                body.session_id,body.question,body.top_k,str(current_user.id),body.document_ids
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except AppException as exc:
            logger.warning(
                "query_stream: upstream error mid-stream",
                session_id=body.session_id,error=exc.__class__.__name__,message=exc.message,
            )
            yield f"data: {json.dumps({'type':'error','message':exc.message})}\n\n"
        except Exception as exc:
            # Anything unanticipated (network failure, bug, etc.) - still
            # end the stream cleanly rather than crash it. The message is
            # deliberately generic; exc's internals aren't safe to hand to
            # the client, but the full exception is still logged here for
            # debugging.
            logger.exception("query_stream: unexpected error mid-stream",session_id=body.session_id)
            yield f"data: {json.dumps({'type':'error','message':'An unexpected error occurred while generating the response.'})}\n\n"

    return StreamingResponse(event_source(),media_type="text/event-stream")