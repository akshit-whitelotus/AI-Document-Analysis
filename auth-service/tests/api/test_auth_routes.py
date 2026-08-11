import pytest
from httpx import AsyncClient,ASGITransport
from app.main import app
from app.dependencies.repository import get_auth_service
from app.services.auth_service import AuthService
from shared.security.oauth import get_current_user,CurrentUser
from tests.fakes import FakeUserRepository,FakeTokenBlacklist

@pytest.fixture
def client():
    shared_repo = FakeUserRepository()
    shared_blacklist=FakeTokenBlacklist()

    def _get_auth_service_override():
        return AuthService(shared_repo,shared_blacklist)
    app.dependency_overrides[get_auth_service] = _get_auth_service_override
    yield AsyncClient(transport=ASGITransport(app=app),base_url="http://test")
    app.dependency_overrides.clear()

REGISTER_PAYLOAD ={
    "first_name":"Ada",
    "last_name":"Lovelace",
    "username":"ada",
    "email":"ada@example.com",
    "password":"supersecret123",
}

@pytest.mark.asyncio
async def test_register_returns_201_and_never_echoes_the_password(client):
    async with client as ac:
        response = await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    body=response.json()
    assert body["email"] == REGISTER_PAYLOAD["email"]
    assert "password" not in body
    assert "password_hash" not in body

@pytest.mark.asyncio
async def test_register_duplicate_email_returns_422(client):
    async with client as ac:
        await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        response= await ac.post(
            "/api/v1/auth/register",
            json={**REGISTER_PAYLOAD,"username":"someone_else","doc_id":"doc-999"}
        )
    assert response.status_code == 422
    assert response.json()["error"] == "ValidationException"

@pytest.mark.asyncio
async def test_login_returns_tokens_for_correct_credentials(client):
    async with client as ac:
        await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        response=await ac.post(
            "/api/v1/auth/login",
            json={"email":REGISTER_PAYLOAD["email"],"password":REGISTER_PAYLOAD["password"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]

@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    async with client as ac :
        await ac.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        response=await ac.post("/api/v1/auth/login",
                      json={"email":REGISTER_PAYLOAD["email"],"password":"not-the-password"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response=await ac.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_me_returns_current_user_when_authenticated(client):
    async with client as ac:
        register_response=await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        user_id = register_response.json()["id"]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id,raw_claims={})

    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as ac:
        response=await ac.get("/api/v1/auth/me",headers={"Authorization":"Bearer whatever "})
    assert response.status_code == 200
    assert response.json()["id"] == user_id

@pytest.mark.asyncio
async def test_logged_out_returns_204(client):
    async with client as ac:
        await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email":REGISTER_PAYLOAD["email"],"password":REGISTER_PAYLOAD["password"]}
        )
        refresh_token=login_response.json()["refresh_token"]
        response=await ac.post("/api/v1/auth/logout",json={"refresh_token":refresh_token})
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_logged_out_refresh_token_cannot_be_reused(client):
    async with client as ac:
        await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email":REGISTER_PAYLOAD["email"],"password":REGISTER_PAYLOAD["password"]}
        )
        refresh_token=login_response.json()["refresh_token"]
        await ac.post("/api/v1/auth/logout",json={"refresh_token":refresh_token})
        response=await ac.post("/api/v1/auth/refresh",json={"refresh_token":refresh_token})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_refresh_rotates_and_rejects_reuse_of_old_token(client):
    async with client as ac:
        await ac.post("/api/v1/auth/register",json=REGISTER_PAYLOAD)
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email":REGISTER_PAYLOAD["email"],"password":REGISTER_PAYLOAD["password"]}
        )
        old_refresh_token=login_response.json()["refresh_token"]
        first_refresh=await ac.post("/api/v1/auth/refresh",json={"refresh_token":old_refresh_token})
        assert first_refresh.status_code == 200
        assert first_refresh.json()["refresh_token"] != old_refresh_token

        second_refresh= await ac.post("/api/v1/auth/refresh",json={"refresh_token":old_refresh_token})
    assert second_refresh.status_code == 401
