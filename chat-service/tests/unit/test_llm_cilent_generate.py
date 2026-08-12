from unittest.mock import AsyncMock,MagicMock
import pytest
from app.services.llm_client import GeminiClient,LLMError,LLMRateLimitedError

class FakeResponse:
    """
    text-only mode (json_body=None) simulates what actually happened in 
    live testing: an upstream (an egress proxy, a load balancer, Gemini
    itself under some failure mode) returning a non-JSON body, e.g a
    pain-text or HTML error page instead of {"error":...}.
    """
    def __init__(self,status_code:int, json_body: dict | None=None, text: str = "",headers:dict | None=None):
        self.status_code= status_code
        self._json_body= json_body
        self.text= text
        self.headers= headers or {}
    def json(self):
        if self._json_body is None:
            raise ValueError("not json")
        return self._json_body

def make_client_with_response(fake_response: FakeResponse) -> GeminiClient:
    client=GeminiClient()
    client._client=MagicMock()
    client._client.post=AsyncMock(return_value=fake_response)
    return client

@pytest.mark.asyncio
async def test_generate_returns_the_text_on_success():
    client = make_client_with_response(
        FakeResponse(200, {"candidates": [{"content": {"parts": [{"text":"the answer"}]}}]})
    )
    assert await client.generate("a prompt") == "the answer"

@pytest.mark.asyncio
async def test_generate_raises_rate_limited_on_429():
    client= make_client_with_response(FakeResponse(429, {"error":"quota exceeded"}))
    with pytest.raises(LLMRateLimitedError):
        await client.generate("a prompt")

@pytest.mark.asyncio
async def test_generate_raises_llm_error_on_other_failures():
    client = make_client_with_response(FakeResponse(500, {"error": "internal error"}))
    with pytest.raises(LLMError):
        await client.generate("a prompt")

@pytest.mark.asyncio
async def test_generate_raises_llm_error_on_unexpected_response_shape():
    client=make_client_with_response(FakeResponse(200, {"unexpected":"shape"}))
    with pytest.raises(LLMError):
        await client.generate("a prompt")

@pytest.mark.asyncio
async def test_generate_requires_api_key(monkeypatch):
    from shared.config.settings import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY","")
    client=GeminiClient()
    with pytest.raises(LLMError):
        await client.generate("a prompt")

@pytest.mark.asyncio
async def test_generate_handles_a_non_json_error_body_instead_of_crashing():
    """
    Regression test: found via live adversial testing when Gemini's 
    domain was unreachable (blocked by network policy) and the resulting
    error response had a plain-text, non-JSON body. generate() previously
    called response.json() unconditionally before checking the status
    code, so this raised an unhandled JSONDecodeError -> a raw 500
    instead of the intended clean LLMError -> 502.
    """
    client=make_client_with_response(
        FakeResponse(403,json_body=None,text="host_not_allowed")
    )
    with pytest.raises(LLMError) as exc_info:
        await client.generate("a prompt")
    assert "host_not_allowed" in str(exc_info.value)

@pytest.mark.asyncio
async def test_generate_handles_a_non_json_success_body_instead_of_crashing():
    """Same defensive handlng, but for a 2xx response that still isn't
    valid JSON - should still fail cleanly as LLMError , not TypeError."""
    client=make_client_with_response(
        FakeResponse(200,json_body=None,text="not json at all")
    )
    with pytest.raises(LLMError):
        await client.generate("a prompt")