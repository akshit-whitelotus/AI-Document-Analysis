from fastapi import APIRouter
from app.embeddings.embedder import embed_query
from app.schemas import SearchRequest,SearchResponse
from app.vectorstore.faiss_store import get_store

router=APIRouter()

@router.post("/",response_model=SearchResponse)
async def search(request:SearchRequest):
    query_vector=embed_query(request.query)
    results=get_store().search(query_vector,top_k=request.top_k)
    return SearchResponse(results=results)