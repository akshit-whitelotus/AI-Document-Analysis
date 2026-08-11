from fastapi import APIRouter,Request,Response
from fastapi.responses import StreamingResponse


router=APIRouter()

def _forward_headers(request:Request) -> dict:
    headers={}
    if auth:=request.headers.get("authorization"):
        headers["authorization"] = auth
    if content_type:=request.headers.get("content-type"):
        headers["content-type"] = content_type
    return headers

async def proxy_auth(path:str,request:Request):
    client=request.app.state.auth_client
    body=await request.body()
    resp=await client.request(
        request.method,f"/api/v1/auth/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

async def proxy_documents(path:str,request:Request):
    client=request.app.state.document_client
    body=await request.body()
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
for _method in ("GET", "POST", "PUT", "DELETE"):
    router.add_api_route("/auth/{path:path}", proxy_auth, methods=[_method])
    router.add_api_route("/documents/{path:path}", proxy_documents, methods=[_method])

# Must be registered BEFORE the /chat/{path:path} catch-all below - Starlette
# matches routes in registration order, and "/chat/query/stream" would
# otherwise also match that catch-all (path="query/stream") and get
# silently buffered by proxy_chat() instead of actually streaming.
router.add_api_route("/chat/query/stream", proxy_chat_query_stream, methods=["POST"])

for _method in ("GET", "POST","PUT"):
    router.add_api_route("/chat/{path:path}", proxy_chat, methods=[_method])