import json
from pathlib import Path
from uuid import UUID,uuid4

from fastapi import UploadFile
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.exceptions.exceptions import NotFoundException,ValidationException,PayloadTooLargeException
from shared.logger.logger import get_logger
from shared.messaging.celery_app import celery_app
from shared.schemas.events import TOPIC_DOCUMENT_UPLOADED

from app.models.document import Document,DocumentStatus
from app.repositories.implementations.document_repository import DocumentRepository
from app.utils.chunker import chunk_text
from app.utils.pdf_extractor import extract_text

ALLOWED_CONTENT_TYPES={"application/pdf"}
UPLOAD_DIR=Path(settings.UPLOAD_DIR)
MAX_UPLOAD_SIZE_BYTES=settings.MAX_PDF_UPLOAD_SIZE_BYTES
UPLOAD_READ_CHUNK_SIZE=1024*1024
logger=get_logger(__name__)

class DocumentService:
    def __init__(self,document_repository:DocumentRepository,worker_client:ServiceClient):
        self.document_repository = document_repository
        self._worker_client=worker_client
        UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    async def upload(self, file:UploadFile,owner_id:UUID) -> Document:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationException("Only PDF files are supported")

        document_id=uuid4()
        storage_path=UPLOAD_DIR / f"{document_id}.pdf"

        # Streamed in fixed-size chunks with a running total, rather than 
        # `shutil.copyfileobj(file.file, out)` in one shot - that trusted
        #  the client completely and would happily write an aribrately
        #  large body straight to disk (and, upstream of this, the gateway
        #  would have already tried to buffer the whole thing into memory -
        #  see proxy_documents' _read_body_with_limit). Aborting mid-stream
        #  here means an oversized file never fully lands on disk even if
        #  it somehow got the past the gateway (e.g. document-service is called
        #  directly, by passing the gateway.) 

        total_bytes=0
        try:
            with storage_path.open("wb") as out:
                while chunk:=await file.read(UPLOAD_READ_CHUNK_SIZE):
                    total_bytes +=len(chunk)
                    if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                        raise PayloadTooLargeException(
                            f"PDF exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB upload limit."
                        )
                    out.write(chunk)
        except PayloadTooLargeException:
            storage_path.unlink(missing_ok=True)
            raise
        document=Document(
            id=document_id,
            owner_id=owner_id,
            filename=file.filename or f"{document_id}.pdf",
            storage_path=str(storage_path),
            content_type=file.content_type,
            status=DocumentStatus.PENDING.value,
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

    async def delete(self,document_id:UUID,owner_id:UUID) -> None:
        document=await self.get(document_id,owner_id=owner_id)

        # 1) Remove the vector store entries first. If ai-worker-service is
        # unreachable, this raises (via ServiceClient's UpstreamServiceError)
        # and we stop here - the document stays fully intact and visible,
        # so the user can just retry, rather than disappearing from their
        # list while its chunks remain silently searchable forever.
        response=await self._worker_client.delete(
            f"/api/v1/internal/documents/{document_id}",
            params={"owner_id":str(owner_id)},
        )
        deleted_chunks=response.json().get("deleted_chunks",0)
        if document.chunk_count and deleted_chunks != document.chunk_count:
            logger.warning(
                "chunk count mismatch on delete",
                document_id=str(document_id),
                expected=document.chunk_count,
                deleted=deleted_chunks,
            )

        # 2) Remove the files on disk. Missing files (e.g. a document that
        # failed before ever writing a chunks sidecar) are not an error -
        # the goal is "make sure it's gone", not "prove it existed".
        storage_path=Path(document.storage_path)
        storage_path.unlink(missing_ok=True)
        (UPLOAD_DIR / f"{document_id}.chunks.json").unlink(missing_ok=True)

        # 3) Only now touch Postgres - by this point everything that could
        # fail already has, so this is safe to do last.
        document.is_deleted=True
        await self.document_repository.update(document)
