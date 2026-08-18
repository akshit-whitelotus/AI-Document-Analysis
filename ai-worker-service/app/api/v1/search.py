from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from app.embeddings.embedder import embed_query
from app.schemas import SearchRequest,SearchResponse
from app.vectorstore.faiss_store import get_store

router=APIRouter()

@router.post("/",response_model=SearchResponse)
async def search(request:SearchRequest):
    # embed_query() (a sentence-transformers forward pass) and
    # FaissStore.search() (numpy/FAISS, plus a threading. Lock acquistion)
    # are both synchronous, CPU-bound calls. Calling them directly inside 
    # this `async def` handler would bloack the entire event loop for their
    # full duration, so no other request - including unrelated / health
    # checks - could be served concurrently on this process. run_in_threadpool
    # moves the blocking work onto a worker thread
    query_vector=await run_in_threadpool(embed_query,request.query)
    results=await run_in_threadpool(get_store().search,query_vector,owner_id=request.owner_id,top_k=request.top_k,document_ids=request.document_ids)
    return SearchResponse(results=results)