"""
Run from chat-service/:
    pytest tests/unit/test_llm_client_stream.py -q
"""
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.services.llm_client import GeminiClient, LLMError, LLMRateLimitedError


def sse_body(*json_payloads: str) -> list[str]:
    """Builds the line-by-line body Gemini's alt=sse endpoint sends -
    each event is a 'data: {...}' line followed by a blank line."""
    lines = []
    for payload in json_payloads:
        lines.append(f"data: {payload}")
        lines.append("")
    return lines


class FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str], error_json: dict | None = None):
        self.status_code = status_code
        self._lines = lines
        self._error_json = error_json or {}
        self.headers = {}

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        pass

    def json(self):
        return self._error_json


def make_client_with_stream_response(fake_response: FakeStreamResponse) -> GeminiClient:
    client = GeminiClient()

    @asynccontextmanager
    async def fake_stream(method, url, **kwargs):
        yield fake_response

    client._client = MagicMock()
    client._client.stream = fake_stream
    return client


@pytest.mark.asyncio
async def test_generate_stream_uses_a_generous_read_timeout_not_the_default_15s():
    """
    Regression test for the same production incident as
    gateway-service's test_chat_query_stream_uses_a_generous_read_timeout_not_the_default_15s:
    a >15s gap between SSE chunks (Gemini's time-to-first-token, or a pause
    mid-generation) is normal for a streaming LLM response, not a hung
    connection. This asserts the call to Gemini explicitly overrides the
    read timeout rather than inheriting the short default meant for
    ordinary buffered requests.
    """
    from shared.config.settings import settings

    client = GeminiClient()
    captured_kwargs = {}

    @asynccontextmanager
    async def capturing_stream(method, url, **kwargs):
        captured_kwargs.update(kwargs)
        yield FakeStreamResponse(200, sse_body('{"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}'))

    client._client = MagicMock()
    client._client.stream = capturing_stream

    async for _ in client.generate_stream("a prompt"):
        pass

    assert "timeout" in captured_kwargs, "streaming call must explicitly override the timeout"
    timeout = captured_kwargs["timeout"]
    assert timeout.read >= 60, f"read timeout ({timeout.read}s) is too short for an LLM stream"
    assert timeout.read > settings.HTTP_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_generate_stream_yields_text_deltas_in_order():
    lines = sse_body(
        '{"candidates":[{"content":{"parts":[{"text":"Hello "}]}}]}',
        '{"candidates":[{"content":{"parts":[{"text":"world"}]}}]}',
    )
    client = make_client_with_stream_response(FakeStreamResponse(200, lines))

    deltas = [d async for d in client.generate_stream("a prompt")]

    assert deltas == ["Hello ", "world"]


@pytest.mark.asyncio
async def test_generate_stream_skips_malformed_and_empty_lines():
    lines = [
        "",  # blank keepalive line
        "data: not valid json",
        'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}',
        "data: ",  # empty payload after prefix
        "some other line",  # not an SSE data line at all
    ]
    client = make_client_with_stream_response(FakeStreamResponse(200, lines))

    deltas = [d async for d in client.generate_stream("a prompt")]

    assert deltas == ["ok"]


@pytest.mark.asyncio
async def test_generate_stream_raises_rate_limited_on_429():
    client = make_client_with_stream_response(
        FakeStreamResponse(429, [], error_json={"error": "quota exceeded"})
    )

    with pytest.raises(LLMRateLimitedError):
        async for _ in client.generate_stream("a prompt"):
            pass


@pytest.mark.asyncio
async def test_generate_stream_raises_llm_error_on_other_failures():
    client = make_client_with_stream_response(
        FakeStreamResponse(500, [], error_json={"error": "internal error"})
    )

    with pytest.raises(LLMError):
        async for _ in client.generate_stream("a prompt"):
            pass


@pytest.mark.asyncio
async def test_generate_stream_requires_api_key(monkeypatch):
    from shared.config.settings import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    client = GeminiClient()

    with pytest.raises(LLMError):
        async for _ in client.generate_stream("a prompt"):
            pass
