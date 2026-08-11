from uuid import UUID

from fastapi import APIRouter

from app.schemas import DeleteDocumentResponse
from app.vectorstore.faiss_store import get_store

router=APIRouter()

@router.delete("/{document_id}",response_model=DeleteDocumentResponse)
async def delete_document(document_id:UUID,owner_id:str):
    deleted_chunks=get_store().delete_document(document_id,owner_id=owner_id)
    return DeleteDocumentResponse(deleted_chunks=deleted_chunks)
