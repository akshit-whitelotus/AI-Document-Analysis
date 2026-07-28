import json,shutil
from pathlib import Path
from uuid import UUID,uuid4

from fastapi import UploadFile
from shared.config.settings import settings
from shared.exceptions.exceptions import NotFoundException,ValidationException
from shared.messaging.celery_app import celery_app
from shared.schemas.events import TOPIC_DOCUMENT_UPLOADED

from app.models.document import Document,DocumentStatus
from app.repositories.implementations.document_repository import DocumentRepository
from app.utils.chunker import chunk_text
from app.utils.pdf_extractor import extract_text

ALLOWED_CONTENT_TYPES={"application/pdf"}
UPLOAD_DIR=Path(settings.UPLOAD_DIR)

class DocumentService:
    def __init__(self,document_repository:DocumentRepository):
        self.document_repository = document_repository
        UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    async def upload(self, file:UploadFile,owner_id:UUID) -> Document:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationException("Only PDF files are supported")

        document_id=uuid4()
        storage_path=UPLOAD_DIR / f"{document_id}.pdf"

        with storage_path.open("wb") as out :
            shutil.copyfileobj(file.file,out)

        document=Document(
            id=document_id,
            owner_id=owner_id,
            filename=file.filename or f"{document_id}.pdf",
            storage_path=str(storage_path),
            content_type=file.content_type,
            status=DocumentStatus.PENDIND.value,
        )
        document=await self.document_repository.create(document)

        try:
            text,page_count=extract_text(str(storage_path))
            chunks=chunk_text(text)
        except Exception as exc:
            document.status=DocumentStatus.FAILED.value
            document.error_message=f"Failed to extract text: {exc}"
            return await self.document_repository.update(document)

        chunks_path=UPLOAD_DIR / f"{document_id}.chunks.json"
        chunks_path.write_text(json.dumps({"chunks":chunks}))

        document.page_count=page_count
        document.chunk_count=len(chunks)
        await self.document_repository.update(document)
        celery_app.send_task(TOPIC_DOCUMENT_UPLOADED,args=[str(document.id)])
        return document

    async def get(self,document_id:UUID,owner_id:UUID) -> Document:
        document=await self.document_repository.get_by_id(document_id)
        if not document or document.owner_id != owner_id or document.is_deleted:
            raise NotFoundException("Document not found")
        return document
    async def list_for_owner(self,owner_id:UUID) -> list[Document]:
        return await self.document_repository.list_by_owner(owner_id)
