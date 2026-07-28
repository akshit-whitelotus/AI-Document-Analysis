from fastapi import Depends
from app.api.deps import DBSession
from app.services.document_service import DocumentService
from app.repositories.implementations.document_repository import (
    DocumentRepository,
)


def get_document_repository(db:DBSession) -> DocumentRepository:
    return DocumentRepository(db)

def get_document_service(document_repository:DocumentRepository=Depends(get_document_repository)) -> DocumentService:
    return DocumentService(document_repository)