from unittest.mock import AsyncMock,MagicMock
import pytest

from app.services.rag_service import RAGService

async def _fake_stream(chunks:list[str]):
    for chunk in chunks:
        yield chunk

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
    # generate_stream() is an async generator function - MagicMock's
    # return_value stands in for "call it, get back an async generator",
    # which is what real code does (it never awaits generate_stream itself,
    # only iterates the generator it returns).
    service._llm_client.generate_stream=MagicMock(return_value=_fake_stream(["This ", "is ", "the answer."]))
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
