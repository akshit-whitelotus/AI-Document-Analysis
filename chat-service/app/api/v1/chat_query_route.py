from fastapi import APIRouter,Request
from app.api.deps import CurrentUserDep
from app.schemas.chat_query import ChatQueryRequest , ChatQueryResponse 

router = APIRouter()

@router.post("/query",response_model=ChatQueryResponse)
async def query(request:Request,current_user:CurrentUserDep,body:ChatQueryRequest):
    rag_service=request.app.state.rag_service
    return await rag_service.answer(body.session_id,body.question,body.top_k,body.document_ids)