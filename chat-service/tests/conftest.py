from unittest.mock import AsyncMock,MagicMock
import pytest

from app.services.rag_service import RAGService

@pytest.fixture
def rag_service_with_mocked_dependencies():
    """
    RAGService.__init__ only builds lazy clients (httpx.AsyncClient , a Redis
    ConnectionPool) - none of them touch the network until a method is 
    called, so it's safe to construct a real RAGService and then swap its
    four collaborators for mocks, rather than reimplementing RAGService's
    internals as a fake.
    """
    service = RAGService()
    service._worker_client = MagicMock()
    service._worker_client.post=AsyncMock()
    service._llm_client = MagicMock()
    service._llm_client.generate=AsyncMock(return_value="This is the answer.")
    service._cache = MagicMock()
    service._cache.get = AsyncMock(return_value = None)
    service._cache.set = AsyncMock()
    service._sessions = MagicMock()
    service._sessions.get=AsyncMock(return_value=None)
    service._sessions.set = AsyncMock()
    return service

def make_search_response(results: list[dict]):
    """Builds a fake httpx.Response-like object for worker_client.post(). """
    response= MagicMock()
    response.json.return_value = {"results":results}
    return response
