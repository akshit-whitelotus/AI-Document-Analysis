import io
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.document_service import DocumentService
from app.models.document import DocumentStatus
from shared.exceptions.exceptions import NotFoundException,ValidationException,PayloadTooLargeException

@pytest.mark.asyncio
async def test_upload_rejects_no_pdf_content_type(fake_document_repository,owner_id,isolated_upload_dir,mock_worker_client):
    service = DocumentService(fake_document_repository, mock_worker_client)
    text_file=UploadFile(
        filename="notes.txt",
        file=io.BytesIO(b"hello"),
        headers=Headers({"content-type":"text/plain"})
    )
    with pytest.raises(ValidationException):
        await service.upload(text_file,owner_id=owner_id)

@pytest.mark.asyncio
async def test_upload_rejects_a_file_over_the_size_limit_and_leaves_no_partial_file(
    fake_document_repository,owner_id,isolated_upload_dir,mock_worker_client,monkeypatch
):
    import app.services.document_service as document_service_module
    # Small limit so the test doesn't need to actually generate megabytes.
    monkeypatch.setattr(document_service_module,"MAX_UPLOAD_SIZE_BYTES",10)

    oversized_file=UploadFile(
        filename="big.pdf",
        file=io.BytesIO(b"%PDF-1.4 " + b"x" *100),
        headers=Headers({"content-type":"application/pdf"})
    )
    service = DocumentService(fake_document_repository,mock_worker_client)
    with pytest.raises(PayloadTooLargeException):
        await service.upload(oversized_file,owner_id=owner_id)

    # Nothing should be left behind for an upload that was rejected mid-stream.
    assert list(isolated_upload_dir.glob("*.pdf")) ==[]
    

@pytest.mark.asyncio
async def test_upload_stores_document_and_queues_processing(fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline,mock_worker_client):
    service = DocumentService(fake_document_repository, mock_worker_client)
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
    fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline,mock_worker_client
):
    mock_processing_pipeline["extract_text"].side_effect = RuntimeError("corrupt PDF")
    service=DocumentService(fake_document_repository, mock_worker_client)
    document=await service.upload(pdf_upload_file,owner_id=owner_id)
    assert document.status == DocumentStatus.FAILED.value
    assert "corrupt PDF" in document.error_message
    mock_processing_pipeline["celery_app"].send_task.assert_not_called()

@pytest.mark.asyncio
async def test_get_returns_document_for_owner(
    fake_document_repository, owner_id, pdf_upload_file,isolated_upload_dir,mock_processing_pipeline,mock_worker_client
):
    service = DocumentService(fake_document_repository, mock_worker_client)
    document= await service.upload(pdf_upload_file,owner_id=owner_id)
    fetched = await service.get(document.id,owner_id=owner_id)
    assert fetched.id == document.id

@pytest.mark.asyncio
async def test_get_hides_documents_belonging_to_other_owners(
    fake_document_repository,owner_id,pdf_upload_file,isolated_upload_dir,mock_processing_pipeline,mock_worker_client
):
    service = DocumentService(fake_document_repository, mock_worker_client)
    document = await service.upload(pdf_upload_file,owner_id=owner_id)

    from uuid import uuid4
    with pytest.raises(NotFoundException):
        await service.get(document.id,owner_id=uuid4())


@pytest.mark.asyncio
async def test_delete_removes_vector_store_entries_files_and_soft_deletes_the_row(
    fake_document_repository, owner_id, pdf_upload_file, isolated_upload_dir, mock_processing_pipeline, mock_worker_client
):
    service = DocumentService(fake_document_repository, mock_worker_client)
    document = await service.upload(pdf_upload_file, owner_id=owner_id)
    pdf_path = isolated_upload_dir / f"{document.id}.pdf"
    chunks_path = isolated_upload_dir / f"{document.id}.chunks.json"
    assert pdf_path.exists() and chunks_path.exists()

    await service.delete(document.id, owner_id=owner_id)

    mock_worker_client.delete.assert_awaited_once_with(
        f"/api/v1/internal/documents/{document.id}", params={"owner_id": str(owner_id)}
    )
    assert not pdf_path.exists()
    assert not chunks_path.exists()
    assert document.is_deleted is True


@pytest.mark.asyncio
async def test_deleted_document_is_no_longer_visible_via_get_or_list(
    fake_document_repository, owner_id, pdf_upload_file, isolated_upload_dir, mock_processing_pipeline, mock_worker_client
):
    service = DocumentService(fake_document_repository, mock_worker_client)
    document = await service.upload(pdf_upload_file, owner_id=owner_id)

    await service.delete(document.id, owner_id=owner_id)

    with pytest.raises(NotFoundException):
        await service.get(document.id, owner_id=owner_id)
    assert document.id not in [d.id for d in await service.list_for_owner(owner_id)]


@pytest.mark.asyncio
async def test_delete_rejects_a_document_belonging_to_another_owner(
    fake_document_repository, owner_id, pdf_upload_file, isolated_upload_dir, mock_processing_pipeline, mock_worker_client
):
    service = DocumentService(fake_document_repository, mock_worker_client)
    document = await service.upload(pdf_upload_file, owner_id=owner_id)

    from uuid import uuid4
    with pytest.raises(NotFoundException):
        await service.delete(document.id, owner_id=uuid4())

    # Nothing should have been touched - no vector-store call, files intact.
    mock_worker_client.delete.assert_not_awaited()
    assert (isolated_upload_dir / f"{document.id}.pdf").exists()


@pytest.mark.asyncio
async def test_delete_leaves_the_document_intact_if_the_vector_store_call_fails(
    fake_document_repository, owner_id, pdf_upload_file, isolated_upload_dir, mock_processing_pipeline, mock_worker_client
):
    """
    If ai-worker-service can't be reached, the document must stay fully
    visible/retryable rather than disappearing while its vectors are
    silently orphaned - see the ordering comment in document_service.py.
    """
    from shared.clients.service_client import UpstreamServiceError

    service = DocumentService(fake_document_repository, mock_worker_client)
    document = await service.upload(pdf_upload_file, owner_id=owner_id)
    mock_worker_client.delete.side_effect = UpstreamServiceError("ai-worker-service unreachable")

    with pytest.raises(UpstreamServiceError):
        await service.delete(document.id, owner_id=owner_id)

    assert document.is_deleted is False
    assert (isolated_upload_dir / f"{document.id}.pdf").exists()
    fetched = await service.get(document.id, owner_id=owner_id)
    assert fetched.id == document.id