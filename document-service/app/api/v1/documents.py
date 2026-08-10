from typing import Annotated
from uuid import UUID

from fastapi import APIRouter,Depends,File,UploadFile,status
from shared.security.oauth import CurrentUserDep
from app.dependencies.repository import get_document_service
from app.schemas.document import DocumentResponse,DocumentUploadResponse
from app.services.document_service import DocumentService

router=APIRouter()

DocumentServiceDep=Annotated[DocumentService,Depends(get_document_service)]

@router.post("/",response_model=DocumentUploadResponse,status_code=status.HTTP_201_CREATED)
async def upload_document(current_user:CurrentUserDep,document_service:DocumentServiceDep,file:UploadFile=File(...)):
    document=await document_service.upload(file,owner_id=current_user.id)
    return DocumentUploadResponse(id=document.id,filename=document.filename,status=document.status)

@router.get("/",response_model=list[DocumentResponse])
async def list_documents(current_user:CurrentUserDep,document_service:DocumentServiceDep):
    return await document_service.list_for_owner(current_user.id)

@router.get("/{document_id}",response_model=DocumentResponse)
async def get_document(document_id:UUID,current_user:CurrentUserDep,document_service:DocumentServiceDep):
    return await document_service.get(document_id,owner_id=current_user.id)
@router.delete("/{document_id}",status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id:UUID,current_user:CurrentUserDep,document_service:DocumentServiceDep):
    await document_service.delete(document_id,owner_id=current_user.id)