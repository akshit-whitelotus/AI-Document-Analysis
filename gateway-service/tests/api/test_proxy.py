import json
from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from tests.conftest import make_upstream_response, make_stream_client

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


@pytest.mark.asyncio
async def test_chat_query_stream_uses_the_streaming_client_not_the_buffered_one(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat/query/stream", json={"question": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # The generic buffered path must never be used for this route - that
    # would defeat the entire point (buffering the whole SSE response
    # before returning it, instead of streaming bytes as they arrive).
    mock_service_clients["chat_client"].request.assert_not_awaited()
    mock_service_clients["chat_client"].stream.assert_called_once()


@pytest.mark.asyncio
async def test_chat_query_stream_forwards_upstream_bytes_through_unchanged(mock_service_clients):
    mock_service_clients["chat_client"].stream = make_stream_client([
        b'data: {"type": "sources", "sources": []}\n\n',
        b'data: {"type": "delta", "text": "Hello"}\n\n',
        b'data: {"type": "done", "cached": false}\n\n',
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/chat/query/stream", json={"question": "hi"})

    assert response.text == (
        'data: {"type": "sources", "sources": []}\n\n'
        'data: {"type": "delta", "text": "Hello"}\n\n'
        'data: {"type": "done", "cached": false}\n\n'
    )


@pytest.mark.asyncio
async def test_chat_query_stream_calls_the_correct_upstream_path(mock_service_clients):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/chat/query/stream", json={"question": "hi"})

    args, kwargs = mock_service_clients["chat_client"].stream.call_args
    assert args[0] == "POST"
    assert args[1] == "/api/v1/chat/query/stream"


@pytest.mark.asyncio
async def test_chat_query_stream_uses_a_generous_read_timeout_not_the_default_15s():
    """
    Regression test for a real production incident: the shared 15s
    HTTP_TIMEOUT_SECONDS default is fine for ordinary buffered requests,
    but httpx's read timeout fires per SSE chunk, not for the whole
    response - a >15s gap between chunks (e.g. Gemini's time-to-first-token)
    is completely normal for a streaming LLM answer, not a hung connection.
    Using the short default here killed legitimate in-progress streams with
    httpx.ReadTimeout. This asserts the streaming call explicitly overrides
    it with something much longer, rather than silently falling back to
    the client's short default.
    """
    from shared.config.settings import settings

    client = MagicMock()
    client.stream = make_stream_client([b"data: {}\n\n"])
    app.state.chat_client = client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/chat/query/stream", json={"question": "hi"})

    _, kwargs = client.stream.call_args
    assert "timeout" in kwargs, "streaming call must explicitly override the timeout"
    timeout = kwargs["timeout"]
    assert timeout.read >= 60, f"read timeout ({timeout.read}s) is too short for an LLM stream"
    assert timeout.read > settings.HTTP_TIMEOUT_SECONDS, (
        "streaming read timeout must be longer than the default HTTP_TIMEOUT_SECONDS "
        "used for ordinary buffered requests"
    )


@pytest.mark.asyncio
async def test_regular_chat_query_still_uses_the_buffered_proxy_not_streaming(mock_service_clients):
    """
    Confirms the new static /chat/query/stream route registration didn't
    accidentally break routing for the pre-existing /chat/query path -
    that one should still go through the ordinary buffered proxy_chat().
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/v1/chat/query", json={"question": "hi"})

    mock_service_clients["chat_client"].request.assert_awaited_once()
    mock_service_clients["chat_client"].stream.assert_not_called()