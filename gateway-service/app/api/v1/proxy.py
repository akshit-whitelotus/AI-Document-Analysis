from fastapi import APIRouter,Request,Response


router=APIRouter()

def _forward_headers(request:Request) -> dict:
    headers={}
    if auth:=request.headers.get("authorization"):
        headers["authorization"] = auth
    return headers

@router.api_route("/auth/{path:path}",methods=["GET","POST","PUT","DELETE"])
async def proxy_auth(path:str,request:Request):
    client=request.app.state.auth_client
    body=await request.body()
    resp=await client.request(
        request.method,f"/api/v1/auth/{path}",content=body,headers=-_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

@router.api_route("/documents/{path:path}",methods=["GET","POST","PUT","DELETE"])
async def proxy_documents(path:str,request:Request):
    client=request.app.state.document_client
    body=await request.body()
    resp=await client.request (
        request.method, f"/api/v1/documents/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")

@router.api_route("/chat/{path:path}",methods=["GET","POST"])
async def proxy_chat(path:str ,request:Request):
    client=request.app.state.chat_client
    body=await request.body()
    resp=await client.request(
        request.method,f"/api/v1/chat/{path}",content=body,headers=_forward_headers(request)
    )
    return Response(content=resp.content,status_code=resp.status_code,media_type="application/json")