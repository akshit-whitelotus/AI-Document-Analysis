from fastapi import APIRouter,Request,Response
from fastapi.responses import StreamingResponse

from shared.config.settings import settings
from shared.exceptions.exceptions import PayloadTooLargeException


router=APIRouter()

def _forward_headers(request:Request) -> dict:
    headers={}
    if auth:=request.headers.get("authorization"):
        headers["authorization"] = auth
    if content_type:=request.headers.get("content-type"):
        headers["content-type"] = content_type
    return headers

async def _read_body_with_limit(request:Request,max_bytes:int) -> bytes:
    """
    Same end result as `await request.body()`, but never holds more than
    max_bytes+1 chunk in memory - it aborts as soon as the running total
    goes over the limit instead of buffering the whole thing first and
    checking after. A Content-Length header over the limit is rejected
    immediately without reading any body at all; a missing/understated
    one (chunked transfer, or a client thaht just lies) is still caught by
    the running total as bytes actually arrive.
    """
    content_length=request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise PayloadTooLargeException(
                    f"Upload exceeds the {max_bytes // (1024*1024)}MB limit for this endpoint"
                )
        except ValueError:
            pass
    chunks:list[bytes] =[]
    total=0
    async for chunk in request.stream():
        total +=len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeException(
                f"Upload exceeds the {max_bytes // (1024*1024)}MB limit for this end point"
            )
        chunks.append(chunk)
    return b"".join(chunks)

async def proxy_auth(path:str,request:Request):
    client=request.app.state.auth_client
    body=await request.body()
    resp=await client.request(
        request.method,f"/api/v1/auth/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

async def proxy_documents(path:str,request:Request):
    client=request.app.state.document_client
    # This is the PDF upload endpoint (POST /documents/) as well as
    # get/list/delete (which have no body worth capping) - the limit only
    # ever engages when there's actually a body large enough to matter.
    # See shared.config.settings.MAX_PDF_UPLOAD_SIZE_BYTES; document-service
    # enforces the same limit again independently in DocumentService.upload
    # (defense-in-depth for anyone calling it directly, bypassing the
    # gateway).
    
    body=await _read_body_with_limit(request,settings.MAX_PDF_UPLOAD_SIZE_BYTES)
    resp=await client.request (
        request.method, f"/api/v1/documents/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

async def proxy_chat(path:str ,request:Request):
    client=request.app.state.chat_client
    body=await request.body()
    resp=await client.request(
        request.method,f"/api/v1/chat/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

import httpx

# Deliberately much more generous than shared.config.settings.HTTP_TIMEOUT_SECONDS
# (15s, fine for ordinary request/response calls). httpx's read timeout fires
# per chunk, not for the whole response - and a >15s gap between SSE chunks
# (e.g. Gemini's time-to-first-token, or a pause mid-generation) is normal
# for a streaming LLM response, not a hung connection. Using the short
# default here was killing legitimate in-progress streams with
# httpx.ReadTimeout. connect/write/pool stay short since those aren't the
# problem - only read needs the long leash.
_STREAM_TIMEOUT=httpx.Timeout(connect=10.0,read=120.0,write=10.0,pool=10.0)

async def proxy_chat_query_stream(request:Request):
    """
    A dedicated streaming path for SSE - NOT handled by proxy_chat() above.
    proxy_chat() buffers the full upstream response via client.request()
    before returning it, which would defeat the entire point of streaming
    (the browser would still wait for the complete answer). This uses
    ServiceClient.stream() instead, forwarding bytes to the client as they
    arrive from chat-service rather than waiting for the response to finish.
    """
    client=request.app.state.chat_client
    body=await request.body()
    headers=_forward_headers(request)

    async def event_source():
        async with client.stream(
            "POST","/api/v1/chat/query/stream",content=body,headers=headers,timeout=_STREAM_TIMEOUT
        ) as upstream:
            async for chunk in upstream.aiter_bytes():
                yield chunk

    return StreamingResponse(event_source(),media_type="text/event-stream")

# Registered per-method (instead of one api_route with methods=[...]) so each
# method gets its own route object and therefore its own unique operationId.
# Sharing one route across methods made FastAPI generate a single operationId
# for all of them, which is invalid OpenAPI and made Swagger UI's "Execute"
# collapse onto whichever method won the collision (previously always PUT).
for _method in ("GET", "POST", "PATCH", "DELETE"):
    router.add_api_route("/auth/{path:path}", proxy_auth, methods=[_method])
    router.add_api_route("/documents/{path:path}", proxy_documents, methods=[_method])

# Must be registered BEFORE the /chat/{path:path} catch-all below - Starlette
# matches routes in registration order, and "/chat/query/stream" would
# otherwise also match that catch-all (path="query/stream") and get
# silently buffered by proxy_chat() instead of actually streaming.
router.add_api_route("/chat/query/stream", proxy_chat_query_stream, methods=["POST"])

for _method in ("GET", "POST","PUT"):
    router.add_api_route("/chat/{path:path}", proxy_chat, methods=[_method])