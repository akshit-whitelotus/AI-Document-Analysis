from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.api.v1 import search as search_module

@pytest.fixture
def mock_store(monkeypatch):
    store=MagicMock()
    store.search.return_value = [
        {"document_id":"doc-1","chunk_index":0,"text":"some matched text","score":0.91}

    ]
    monkeypatch.setattr(search_module,"get_store",lambda: store)
    return store

@pytest.mark.asyncio
async def test_search_route_returns_reslts_from_the_store(mock_store):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/internal/search/",
            json={"query":"revenue growth", "top_k":5 ,"document_ids":None, "owner_id":"user-abc"}

        )
        assert response.status_code == 200
        assert response.json()["results"][0]["document_id"] == "doc-1"

@pytest.mark.asyncio
async def test_search_route_passes_owner_id_through_to_the_store(mock_store):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        await ac.post(
            "/api/v1/internal/search/",
            json={"query":"revenue growth","top_k": 5, "document_ids":None, "owner_id":"user-abc"},
        )
    _,kwargs = mock_store.search.call_args
    assert kwargs.get("owner_id") == "user-abc"

@pytest.mark.asyncio
async def test_search_route_requires_owner_id_in_the_request_body(mock_store):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        response = await ac.post(
            "/api/v1/internal/search/",
            json={"query":"revenue growth" , "top_k": 5}
        )
        # owner_id must be a required field on SearchRequest - if it's optional,
        # a caller (or a bug in chat-service) could silently omit it and get an
        # unscoped search instead of a clear 422.
        assert response.status_code == 422