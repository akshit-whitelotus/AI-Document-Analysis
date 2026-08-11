import pytest
from app.schemas.user import UserCreate
from app.models.user import Role,DocType
from tests.fakes import FakeUserRepository,FakeTokenBlacklist

@pytest.fixture
def fake_user_repository():
    return FakeUserRepository()

@pytest.fixture
def fake_token_blacklist():
    return FakeTokenBlacklist()

@pytest.fixture
def valid_user_create():
    return UserCreate(
        first_name="Ada",
        last_name="Lovelace",
        username="ada",
        email="ada@example.com",
        password="supersecret123",
    )

