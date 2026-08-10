from unittest.mock import patch
from uuid import uuid4
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.dependencies.repository import get_document_service
from app.services.document_service import DocumentService
from shared.security.oauth import get_current_user, CurrentUser
from tests.fakes import FakeDocumentRepository

@pytest.fixture
def current_user_id():
    return uuid4()

@pytest.fixture
def client(current_user_id,isolated_upload_dir):
    shared_repo = FakeDocumentRepository()
    app.dependency_overrides[get_document_service] = lambda: DocumentService(shared_repo)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=current_user_id,raw_claims={})
    yield AsyncClient(transport=ASGITransport(app=app),base_url="http://test")
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_upload_then_list_then_get(client):
    with patch("app.services.document_service.extract_text",return_value=("some text",1)), \
         patch("app.services.document_service.chunk_text",return_value=["some text"]), \
         patch("app.services.document_service.celery_app"):
        async with client as ac:
            upload_response = await ac.post(
                "/api/v1/documents/",
                files={"file": ("report.pdf", b"%PDF-1.4 fake content", "application/pdf")}
            )
            assert upload_response.status_code == 201
            document_id = upload_response.json()["id"]

            list_response = await ac.get("/api/v1/documents/")
            assert list_response.status_code == 200
            assert any(d["id"] == document_id for d in list_response.json())

            get_response=await ac.get(f"/api/v1/documents/{document_id}")
            assert get_response.status_code == 200
            # upload() only queues processing - it stays "pending" here because
            # celery_app is mocked out, so the worker never actually runs.
            assert get_response.json()["status"] == "pending"

@pytest.mark.asyncio
async def test_upload_rejects_non_pdf(client):
    async with client as ac:
        response = await ac.post(
            "/api/v1/documents/",
            files={"file": ("notes.txt",b"Hello","text/plain")}
        )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_get_unknown_document_returns_404(client):
    async with client as ac:
        response = await ac.get(f"/api/v1/documents/{uuid4()}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_user_cannot_fetch_another_users_document(client,current_user_id):
    with patch("app.services.document_service.extract_text",return_value=("some text",1)), \
         patch("app.services.document_service.chunk_text",return_value=["some text"]), \
         patch("app.services.document_service.celery_app"):
        async with client as ac:
            upload_response = await ac.post(
                "/api/v1/documents/",
                files={"file":("report.pdf" , b"%PDF-1.4 fake content", "application/pdf")},
            )
            document_id = upload_response.json()["id"]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uuid4(),raw_claims={})
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        response = await ac.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 404
