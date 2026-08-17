from uuid import UUID

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.schemas import DeleteDocumentResponse
from app.vectorstore.faiss_store import get_store

router=APIRouter()

@router.delete("/{document_id}",response_model=DeleteDocumentResponse)
async def delete_document(document_id:UUID,owner_id:str):
    # Same reasoning as search.py: FaissStoe.delete_document() is
    # synchronous FAISS/disk I/O under a lock - run it off the event loop.
    deleted_chunks=await run_in_threadpool(get_store().delete_document(document_id,owner_id=owner_id))
    return DeleteDocumentResponse(deleted_chunks=deleted_chunks)
