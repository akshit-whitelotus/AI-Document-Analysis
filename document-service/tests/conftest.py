import io 
from unittest.mock import patch
from uuid import uuid4
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from tests.fakes import FakeDocumentRepository

@pytest.fixture
def fake_document_repository():
    return FakeDocumentRepository()

@pytest.fixture
def owner_id():
    return uuid4()

@pytest.fixture
def pdf_upload_file():
    # Content doesn't need to be a real PDF for unit tests that mock out
    # extract_text() - only the API-level test (which goes through the real
    # pipline) needs an actual PDF, see test_document_routes.py.
    return UploadFile(
        filename="report.pdf",
        file=io.BytesIO(b"%PDF-1.4 fake content"),
        headers=Headers({"content-type":"application/pdf"})
    )

@pytest.fixture
def isolated_upload_dir(tmp_path,monkeypatch):
    """
    document_service.py resolves UPLOAD_DIR from settings at the import time and
    mkdir's it in DocumentService.__init__(). Point that at a throwaway
    tmp_path for every test so nothing is ever written into the real
    ./uploads directory.
    """
    import app.services.document_service as document_service_module
    monkeypatch.setattr(document_service_module, "UPLOAD_DIR",tmp_path)
    return tmp_path

@pytest.fixture
def mock_processing_pipeline():
    """
    Stubs out the pieces of DocumentService.upload() that need real 
    infrastructure (PDF parsing, RabbitMQ) so unit tests can focus on the
    service's own logic (valdation, status transitions , persistence calls).
    """
    with patch("app.services.document_service.extract_text") as extract_text, \
         patch("app.services.document_service.chunk_text") as chunk_text, \
         patch("app.services.document_service.celery_app") as celery_app:
        extract_text.return_value = ("Some extracted text.",1)
        chunk_text.return_value=["Some extracted text."]
        yield {"extract_text":extract_text,"chunk_text":chunk_text,"celery_app":celery_app}
