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
    rag_service = request.app.state.rag_service
    async def event_generator():
        try:
            yield "event : start\n"
            yield "data: {}\n\n"
            async for token in rag_service.answer_stream(
                session_id=body.session_id,
                question=body.question,
                top_k=body.top_k,
                owner_id=str(current_user.id),
                document_ids=body.document_ids
            ):
                if await request.is_disconnected():
                    break
                yield f"event: token\n"
                yield (
                    f"data: {json.dumps(token['data'],ensure_ascii=False)}\n\n"
                )
            yield "event: done\n"
            yield "data: {}\n\n"
        except Exception as exc:
            yield "event: error\n"
            yield (
                f"data: {json.dumps({'message': str(exc)},ensure_ascii=False)}\n\n"
            )
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection" : "keep-alive",
            "X-Accel-Buffering" : "no"
        }
    )