import hashlib
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.exceptions.exceptions import AppException

class LLMError(AppException):
    status_code=502

class GeminiClient:
    def __init__(self):
        self._client=ServiceClient(base_url=settings.GEMINI_BASE_URL)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(self,prompt:str) -> str :
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not configured")

        url=f"/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        body={"contents":[{"parts": [{"text":prompt}]}]}

        response=await self._client.post(url,json=body)
        data=response.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError,IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc

def prompt_cache_key(question:str,context:str) -> str:
    digest=hashlib.sha256(f"{question}|{context}".encode()).hexdigest()
    return f"llm_response:{digest}"
