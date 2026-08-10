from unittest.mock import AsyncMock,MagicMock
from contextlib import asynccontextmanager
import pytest
import httpx
from app.main import app
from app.core import rate_limit as rate_limit_module

@pytest.fixture(autouse=True)
def bypass_rate_limiting(monkeypatch):
    """
    RateLimitMiddleware is attached to the app globally (app.add_middleware),
    so every request - even ones that have nothing to do with rate limiting - 
    goes through it. Its `_limiter` is a module-level RateLimiter instance
    that talks to real Redis via shared.cache.redis_client. Patch it to
    always allow, so tests don't need Redis running. The one test that
    actually exercises rate limiting overrides this again with a stricter
    fake - see tests/unit/test_rate_limit.py
    """
    monkeypatch.setattr(
        rate_limit_module._limiter , "is_allowed",AsyncMock(return_value=(True,999))

    )
def make_upstream_response(status_code: int = 200 , json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET","http://upstream.test/")
    return httpx.Response(status_code,json=json_body if json_body is not None else {} , request=request)

class _FakeStreamingUpstream:
    """Stands in for the httpx.Response yielded by client.stream(...)."""
    def __init__(self, chunks: list[bytes], status_code: int = 200):
        self.status_code = status_code
        self._chunks = chunks
    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

def make_stream_client(chunks: list[bytes]):
    """
    A callable matching ServiceClient.stream()'s signature: NOT an async
    function itself - it returns an async context manager synchronously,
    the same way httpx.AsyncClient.stream() and our ServiceClient.stream()
    passthrough both do.
    """
    @asynccontextmanager
    async def _stream(method, url, **kwargs):
        yield _FakeStreamingUpstream(chunks)
    return MagicMock(side_effect=_stream)

@pytest.fixture
def mock_service_clients():
    """
    Sets app.state.{auth,document,chat}_client to mocks (the gateway proxy
    reads them from app.state, set during lifespan - same pattern as 
    chat-service's rag_service). Each mock's .request()  is an AsyncMock
    returning a 200 by default; override per-test as needed.
    """
    clients = {
        "auth_client":MagicMock(request=AsyncMock(return_value=make_upstream_response())),
        "document_client":MagicMock(request=AsyncMock(return_value=make_upstream_response())),
        "chat_client":MagicMock(request=AsyncMock(return_value=make_upstream_response()))
    }
    clients["chat_client"].stream = make_stream_client([b'data: {"type": "sources", "sources": []}\n\n'])
    app.state.auth_client = clients["auth_client"]
    app.state.document_client = clients["document_client"]
    app.state.chat_client = clients["chat_client"]
    return clients