import json
from fastapi import APIRouter,Request
from fastapi.responses import StreamingResponse
from app.api.deps import CurrentUserDep
from app.schemas.chat_query import ChatQueryRequest , ChatQueryResponse 

router = APIRouter()

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