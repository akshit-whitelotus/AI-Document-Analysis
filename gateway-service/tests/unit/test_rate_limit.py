from unittest.mock import AsyncMock
import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.core import rate_limit as rate_limit_module

@pytest.mark.asyncio
async def test_allowed_request_passes_through_and_sets_remaining_header(monkeypatch):
    monkeypatch.setattr(rate_limit_module._limiter,"is_allowed",AsyncMock(return_value=(True,42)))

    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response= await ac.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.headers["x-ratelimit-remaining"] == "42"

@pytest.mark.asyncio
async def test_blocked_request_returns_429_with_expected_body(monkeypatch):
    monkeypatch.setattr(rate_limit_module._limiter,"is_allowed",AsyncMock(return_value=(False,0)))

    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response = await ac.get("/api/v1/health/")
    assert response.status_code == 429
    assert response.json() == {
        "error":"RateLimitExceeded",
        "message":"Too many requests,slow down."
    }

@pytest.mark.asyncio
async def test_identity_prefers_authorization_header_over_client_ip(monkeypatch):
    is_allowed = AsyncMock(return_value =(True,10))
    monkeypatch.setattr(rate_limit_module._limiter , "is_allowed",is_allowed)

    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac :
        await ac.get("/api/v1/health/",headers={"Authorization":"Bearer same-user-token"})
        await ac.get("/api/v1/health/",headers={"Authorization":"Bearer same-user-token"})

    # Both calls should be rate-limited under the *same* identity (the
    # token), regardless of which client/connection made the request -
    # otherwise a user behind a shared/rotating IP could dodge limits, or
    # unrelated users behind the same IP could rate-limit each other.
    first_identity= is_allowed.await_args_list[0].args[0]
    second_identity=is_allowed.await_args_list[1].args[0]
    assert first_identity == second_identity == "Bearer same-user-token"
