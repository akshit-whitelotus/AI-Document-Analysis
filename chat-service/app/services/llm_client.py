import asyncio
import hashlib
import httpx
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.exceptions.exceptions import AppException

class LLMError(AppException):
    status_code=502

class LLMRateLimitedError(AppException):
    """Gemini returned 429 - quota/rate limit hit after retries were exhausted."""
    status_code=429

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
        data = response.json()

        if response.status_code == 429:
            raise LLMRateLimitedError(
                "Gemini API rate limit / quota exceeded. Please try again shortly."
            )
        if response.status_code >= 400:
            raise LLMError(f"Gemini API error {response.status_code}: {data}")

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError,IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc

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