"""
Run from ai-worker-service/:
    pytest tests/api/test_documents_internal_routes.py -q
"""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.v1 import documents_internal as documents_internal_module


@pytest.fixture
def mock_store(monkeypatch):
    store = MagicMock()
    store.delete_document.return_value = 3
    monkeypatch.setattr(documents_internal_module, "get_store", lambda: store)
    return store


@pytest.mark.asyncio
async def test_delete_route_returns_deleted_chunk_count(mock_store):
    document_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.delete(
            f"/api/v1/internal/documents/{document_id}", params={"owner_id": "user-abc"}
        )

    assert response.status_code == 200
    assert response.json()["deleted_chunks"] == 3


@pytest.mark.asyncio
async def test_delete_route_passes_document_id_and_owner_id_through_to_the_store(mock_store):
    document_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.delete(f"/api/v1/internal/documents/{document_id}", params={"owner_id": "user-abc"})

    args, kwargs = mock_store.delete_document.call_args
    assert str(args[0]) == str(document_id)
    assert kwargs.get("owner_id") == "user-abc"


@pytest.mark.asyncio
async def test_delete_route_requires_owner_id(mock_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.delete(f"/api/v1/internal/documents/{uuid4()}")

    # owner_id must be required - a caller forgetting it should get a clear
    # 422, not a delete_document() call with owner_id=None reaching the store.
    assert response.status_code == 422
    mock_store.delete_document.assert_not_called()
