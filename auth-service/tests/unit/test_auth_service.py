import pytest
from app.services.auth_service import AuthService
from app.schemas.user import UserLogin
from shared.exceptions.exceptions import UnauthorizedException,ValidationException
from shared.security.hashing import verify_password
from shared.security.jwt import decode_token

@pytest.mark.asyncio
async def test_register_creates_user_with_hashed_password(fake_user_repository,valid_user_create,fake_token_blacklist):
    service = AuthService(fake_user_repository,fake_token_blacklist)
    user=await service.register(valid_user_create)
    assert user.email == valid_user_create.email
    assert user.password_hash != valid_user_create.password
    assert verify_password(valid_user_create.password,user.password_hash)

@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(fake_user_repository,valid_user_create,fake_token_blacklist):
    service = AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)
    duplicate=valid_user_create.model_copy(update={"username":"someone_else"})
    with pytest.raises(ValidationException):
        await service.register(duplicate)

@pytest.mark.asyncio
async def test_register_rejects_duplicate_username(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)

    duplicate=valid_user_create.model_copy(update={"email":"other@example.com"})

    with pytest.raises(ValidationException):
        await service.register(duplicate)

@pytest.mark.asyncio
async def test_login_succeeds_with_correct_credentials(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)
    token=await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))
    assert token.access_token
    assert token.refresh_token

@pytest.mark.asyncio
async def test_login_rejects_wrong_password(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)

    with pytest.raises(UnauthorizedException):
        await service.login(UserLogin(email=valid_user_create.email,password="wrong-password"))

@pytest.mark.asyncio
async def test_login_rejects_unknown_email(fake_user_repository,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    with pytest.raises(UnauthorizedException):
        await service.login(UserLogin(email="nobody@example.com",password="whatever1234"))

@pytest.mark.asyncio
async def test_login_rejects_disabled_account(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    user=await service.register(valid_user_create)
    user.is_active =False
    with pytest.raises(UnauthorizedException):
        await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))

@pytest.mark.asyncio
async def test_refresh_issues_a_valid_access_token(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    user=await service.register(valid_user_create)
    login_tokens=await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))
    new_tokens= await service.refresh(login_tokens.refresh_token)

    assert new_tokens.access_token
    assert new_tokens.refresh_token
    payload= decode_token(new_tokens.access_token,expected_type="access")
    assert payload["sub"] == str(user.id)

@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token(fake_user_repository,valid_user_create,fake_token_blacklist):
    service = AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)
    login_tokens= await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))
    with pytest.raises(UnauthorizedException):
        await service.refresh(login_tokens.access_token)

@pytest.mark.asyncio
async def test_refresh_rotates_and_rejects_reuse_of_the_old_refresh_token(fake_user_repository,fake_token_blacklist,valid_user_create):
    service = AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)
    login_tokens=await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))

    new_tokens=await service.refresh(login_tokens.refresh_token)
    assert new_tokens.refresh_token !=login_tokens.refresh_token

    with pytest.raises(UnauthorizedException):
        await service.refresh(login_tokens.refresh_token)

@pytest.mark.asyncio
async def test_logout_revokes_the_refresh_token(fake_user_repository,valid_user_create,fake_token_blacklist):
    service=AuthService(fake_user_repository,fake_token_blacklist)
    await service.register(valid_user_create)
    login_tokens= await service.login(UserLogin(email=valid_user_create.email,password=valid_user_create.password))

    await service.logout(login_tokens.refresh_token)

    with pytest.raises(UnauthorizedException):
        await service.refresh(login_tokens.refresh_token)