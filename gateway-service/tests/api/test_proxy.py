import json
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from tests.conftest import make_upstream_response

@pytest.mark.asyncio
async def test_get_is_forwarded_to_auth_client_with_correct_path(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me",headers={"Authorization":"Bearer abc123"})
    assert response.status_code == 200
    mock_service_clients["auth_client"].request.assert_awaited_once()
    method, url = mock_service_clients["auth_client"].request.await_args.args
    assert method == "GET"
    assert url == "/api/v1/auth/me"

@pytest.mark.asyncio
async def test_post_body_is_forwarded_unchanged_to_document_client(mock_service_clients):
    payload={"hello":"world"}
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        response = await ac.post("/api/v1/documents/some/nested/path",json=payload)
    assert response.status_code == 200
    mock_service_clients["document_client"].request.assert_awaited_once()
    _,url = mock_service_clients["document_client"].request.await_args.args
    kwargs = mock_service_clients["document_client"].request.await_args.kwargs
    assert url == "/api/v1/documents/some/nested/path"
    assert json.loads(kwargs["content"]) == payload

@pytest.mark.asyncio
async def test_chat_query_is_forwarded_to_chat_client(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat/query",json={"question":"hi"})
    assert response.status_code == 200
    mock_service_clients["chat_client"].request.assert_awaited_once()
    _,url = mock_service_clients["chat_client"].request.await_args.args
    assert url == "/api/v1/chat/query"

@pytest.mark.asyncio
async def test_only_authorization_and_content_type_headers_are_forwarded(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        await ac.post(
            "/api/v1/auth/login",
            json={"email":"a@b.com","password":"x"},
            headers={
                "Authorization":"Bearer abc123",
                "X-Secret-Internal-Header": "this-must-not-leak-upstream",
                "Cookie":"session=should-not-be-forwarded-either"
            },
        )
    forwarded_headers=mock_service_clients["auth_client"].request.await_args.kwargs["headers"]
    assert forwarded_headers.get("authorization") == "Bearer abc123"
    assert 'x-secret-internal-header' not in {k.lower() for k in forwarded_headers}
    assert "cokkie" not in {k.lower() for k in forwarded_headers}

@pytest.mark.asyncio
async def test_upstream_error_status_and_body_pass_through_unchanges(mock_service_clients):
    mock_service_clients["auth_client"].request.return_value = make_upstream_response(
        status_code=404,json_body={"error":"NotFoundException","message":"User not found"}
    )
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response=await ac.get("/api/v1/auth/users/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"error":"NotFoundException","message":"User not found"}

@pytest.mark.asyncio
async def test_health_endpoint_does_not_touch_any_downstream_service(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response = await ac.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    mock_service_clients["auth_client"].request.assert_not_awaited()
    mock_service_clients["document_client"].request.assert_not_awaited()
    mock_service_clients["chat_client"].request.assert_not_awaited()