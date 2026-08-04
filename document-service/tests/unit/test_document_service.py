import io
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.document_service import DocumentService
from app.models.document import DocumentStatus
from shared.exceptions.exceptions import NotFoundException,ValidationException

@pytest.mark.asyncio
async def test_upload_rejects_no_pdf_content_type(fake_document_repository,owner_id,isolated_upload_dir):
    service = DocumentService(fake_document_repository)
    text_file=UploadFile(
        filename="notes.txt",
        file=io.BytesIO(b"hello"),
        headers=Headers({"content-type":"text/plain"})
    )
    with pytest.raises(ValidationException):
        await service.upload(text_file,owner_id=owner_id)

@pytest.mark.asyncio
async def test_upload_stores_document_and_queues_processing(fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline):
    service = DocumentService(fake_document_repository)
    document = await service.upload(pdf_upload_file,owner_id=owner_id)

    assert document.status == DocumentStatus.PENDING.value
    assert document.owner_id == owner_id
    assert document.chunk_count == 1
    assert (isolated_upload_dir /f"{document.id}.pdf").exists()
    assert (isolated_upload_dir /f"{document.id}.chunks.json").exists()
    mock_processing_pipeline["celery_app"].send_task.assert_called_once_with(
        "document.uploaded",args=[str(document.id)]
    )

@pytest.mark.asyncio
async def test_upload_marks_document_failed_when_text_extraction_raises(
    fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline
):
    mock_processing_pipeline["extract_text"].side_effect = RuntimeError("corrupt PDF")
    service=DocumentService(fake_document_repository)
    document=await service.upload(pdf_upload_file,owner_id=owner_id)
    assert document.status == DocumentStatus.FAILED.value
    assert "corrupt PDF" in document.error_message
    mock_processing_pipeline["celery_app"].send_task.assert_not_called()

@pytest.mark.asyncio
async def test_get_returns_document_for_owner(
    fake_document_repository, owner_id, pdf_upload_file,isolated_upload_dir,mock_processing_pipeline
):
    service = DocumentService(fake_document_repository)
    document= await service.upload(pdf_upload_file,owner_id=owner_id)
    fetched = await service.get(document.id,owner_id=owner_id)
    assert fetched.id == document.id

@pytest.mark.asyncio
async def test_get_hides_documents_belonging_to_other_owners(
    fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline
):
    service = DocumentService(fake_document_repository)
    document = await service.upload(pdf_upload_file,owner_id=owner_id)

    from uuid import uuid4
    with pytest.raises(NotFoundException):
        await service.get(document.id,owner_id=uuid4())