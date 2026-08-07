from typing import Any,AsyncContextManager
import httpx
from tenacity import retry,retry_if_exception_type,stop_after_attempt,wait_exponential_jitter
from shared.config.settings import settings
from shared.exceptions.exceptions import AppException

class UpstreamServiceError(AppException):
    status_code=502

def _timeout() -> httpx.Timeout:
    t=settings.HTTP_TIMEOUT_SECONDS
    return httpx.Timeout(connect=t,read=t,write=t,pool=t)

RETRYABLE_EXCEPTION=(
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout
)

class ServiceClient:
    def __init__(self,base_url:str=""):
        self._base_url=base_url
        self._client=httpx.AsyncClient(base_url=base_url,timeout=_timeout())
    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.HTTP_MAX_RETRIES),
        wait=wait_exponential_jitter(initial=0.5,max=4),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTION),
    )
    async def _send(self,method:str,url:str,**kwargs:Any) -> httpx.Response:
        response=await self._client.request(method,url,**kwargs)
        if response.status_code >=500:
            raise httpx.HTTPStatusError(
                f"Upstream {url} returned {response.status_code}",
                request=response.request,
                response=response
            )
        return response
    async def _request(self,method:str,url:str,**kwargs:Any) -> httpx.Response:
        try:
            return await self._send(method,url,**kwargs)
        except (httpx.HTTPStatusError,*RETRYABLE_EXCEPTION) as exc :
            raise UpstreamServiceError(f"Failed to reach {self._base_url}{url}: {exc}") from exc
    async def request(self,method:str,url:str,**kwargs:Any) -> httpx.Response:
        return await self._request(method,url,**kwargs)
    async def get(self,url:str,**kwargs:Any) -> httpx.Response:
        return await self._request("GET",url,**kwargs)
    async def post(self,url:str,**kwargs:Any) -> httpx.Response:
        return await self._request("POST",url,**kwargs)
    async def put(self,url:str,**kwargs:Any) -> httpx.Response:
        return await self._request("PUT",url,**kwargs)
    async def delete(self,url:str,**kwargs:Any) -> httpx.Response:
        return await self._request("DELETE",url,**kwargs)
    def stream(self,method:str,url:str,**kwargs:Any) -> AsyncContextManager[httpx.Response]:
        return self._client.stream(method,url,**kwargs)
        