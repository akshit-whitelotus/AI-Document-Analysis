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
async def proxy_chat_stream(request:Request):
    client=request.app.state.chat_client
    body=await request.body()
    async def stream_response():
        async with client.stream("POST","/api/v1/chat/query/stream",content=body,headers=_forward_headers(request)) as upstream:
            async for chunk in upstream.aiter_bytes():
                if await request.is_disconnected():
                    break
                yield chunk
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":"no-cache",
            "Connection":"keep-alive",
            "X-Accel-Buffering":"no"
        }
    )


# Registered per-method (instead of one api_route with methods=[...]) so each
# method gets its own route object and therefore its own unique operationId.
# Sharing one route across methods made FastAPI generate a single operationId
# for all of them, which is invalid OpenAPI and made Swagger UI's "Execute"
# collapse onto whichever method won the collision (previously always PUT).
for _method in ("GET", "POST", "PUT", "DELETE"):
    router.add_api_route("/auth/{path:path}", proxy_auth, methods=[_method])
    router.add_api_route("/documents/{path:path}", proxy_documents, methods=[_method])
router.add_api_route("/chat/query/stream",proxy_chat_stream,methods=["POST"])
for _method in ("GET", "POST"):
    router.add_api_route("/chat/{path:path}", proxy_chat, methods=[_method])
