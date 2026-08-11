import json
from fastapi import APIRouter,Request
from fastapi.responses import StreamingResponse
from app.api.deps import CurrentUserDep
from app.schemas.chat_query import ChatQueryRequest , ChatQueryResponse,SessionDocumentRequest,SessionDocumentResponse

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
    document_ids = await rag_service.set_session_documents(session_id,body.document_ids)
    return SessionDocumentResponse(session_id=session_id,document_ids=document_ids)

@router.get("/sessions/{session_id}/documents",response_model=SessionDocumentResponse)
async def get_session_documents(session_id:str,request:Request,current_user:CurrentUserDep):
    rag_service = request.app.state.rag_service
    document_ids=await rag_service.get_session_documents(session_id) or []
    return SessionDocumentResponse(session_id=session_id,document_ids=document_ids)
@router.post("/query",response_model=ChatQueryResponse)
async def query(request:Request,current_user:CurrentUserDep,body:ChatQueryRequest):
    rag_service=request.app.state.rag_service
    return await rag_service.answer(body.session_id,body.question,body.top_k,str(current_user.id),body.document_ids)

@router.post("/query/stream")
async def query_stream(request:Request,current_user:CurrentUserDep,body:ChatQueryRequest):
    rag_service=request.app.state.rag_service

    async def event_source():
        async for event in rag_service.answer_stream(
            body.session_id,body.question,body.top_k,str(current_user.id),body.document_ids
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_source(),media_type="text/event-stream")