import asyncio
import hashlib
import json
import httpx
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.exceptions.exceptions import AppException

class LLMError(AppException):
    status_code=502

class LLMRateLimitedError(AppException):
    """Gemini returned 429 - quota/rate limit hit after retries were exhausted."""
    status_code=429

# Deliberately much more generous than shared.config.settings.HTTP_TIMEOUT_SECONDS
# (15s, fine for ordinary request/response calls). httpx's read timeout fires
# per chunk, not for the whole response - and a >15s gap between SSE chunks
# (Gemini's time-to-first-token, or a pause mid-generation) is normal for a
# streaming LLM response, not a hung connection. Using the short default
# here was killing legitimate in-progress streams with httpx.ReadTimeout.
_STREAM_TIMEOUT=httpx.Timeout(connect=10.0,read=120.0,write=10.0,pool=10.0)

class GeminiClient:
    # Retries within a single request for transient 429s. Gemini's free-tier
    # quota errors are often per-minute, so a couple of short backoffs can
    # ride out a brief burst without failing the user's request outright.
    _MAX_RATE_LIMIT_RETRIES = 3

    def __init__(self):
        self._client=ServiceClient(base_url=settings.GEMINI_BASE_URL)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(self,prompt:str) -> str :
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not configured")

        url=f"/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        body={"contents":[{"parts": [{"text":prompt}]}]}

        response = await self._post_with_rate_limit_retry(url, body)

        # Gemini (or anything sitting in front of it - a proxy, a load
        # balancer, a network-policy block) doesn't guarantee a JSON body
        # on every response, especially error ones. generate_stream() below
        # already accounts for this; this used to call response.json()
        # unconditionally and let a plain-text error body raise an
        # unhandled JSONDecodeError straight through to the caller as a
        # raw 500, instead of the intended clean LLMError/502.
        try:
            data = response.json()
        except ValueError:
            data = response.text

        if response.status_code == 429:
            raise LLMRateLimitedError(
                "Gemini API rate limit / quota exceeded. Please try again shortly."
            )
        if response.status_code >= 400:
            raise LLMError(f"Gemini API error {response.status_code}: {data}")

        if not isinstance(data, dict):
            raise LLMError(f"Unexpected Gemini response shape: {data}")
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError,IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc

    async def generate_stream(self,prompt:str):
        """
        Yields text deltas as they arrive from Gemini's streamGenerateContent
        endpoint (NOT generateContent - a different endpoint entirely, with
        alt=sse to get server-sent-event framing rather than a single JSON
        array). No rate-limit retry here, unlike generate() - retrying after
        some deltas have already been yielded to the caller would mean the
        caller sees the same text twice, so a 429 here is raised immediately.
        """
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not configured")

        url=f"/models/{settings.GEMINI_MODEL}:streamGenerateContent?alt=sse&key={settings.GEMINI_API_KEY}"
        body={"contents":[{"parts": [{"text":prompt}]}]}

        async with self._client.stream("POST",url,json=body,timeout=_STREAM_TIMEOUT) as response:
            if response.status_code >= 400:
                await response.aread()
                try:
                    data=response.json()
                except ValueError:
                    data=response.text
                if response.status_code == 429:
                    raise LLMRateLimitedError(
                        "Gemini API rate limit / quota exceeded. Please try again shortly."
                    )
                raise LLMError(f"Gemini API error {response.status_code}: {data}")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload=line[len("data: "):].strip()
                if not payload:
                    continue
                try:
                    chunk=json.loads(payload)
                    text=chunk["candidates"][0]["content"]["parts"][0]["text"]
                except (json.JSONDecodeError,KeyError,IndexError):
                    continue
                if text:
                    yield text

    async def _post_with_rate_limit_retry(self, url: str, body: dict) -> httpx.Response:
        delay = 1.0
        for attempt in range(self._MAX_RATE_LIMIT_RETRIES + 1):
            response = await self._client.post(url, json=body)
            if response.status_code != 429:
                return response
            if attempt == self._MAX_RATE_LIMIT_RETRIES:
                return response
            # Respect Gemini's Retry-After header when it's provided,
            # otherwise fall back to a short exponential backoff.
            retry_after = response.headers.get("retry-after")
            wait_seconds = float(retry_after) if retry_after else delay
            await asyncio.sleep(wait_seconds)
            delay *= 2
        return response

def prompt_cache_key(question:str,context:str) -> str:
    digest=hashlib.sha256(f"{question}|{context}".encode()).hexdigest()
    return f"llm_response:{digest}"