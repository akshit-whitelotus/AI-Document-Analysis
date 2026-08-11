from fastapi import Depends

from app.api.deps import DBSession
from app.repositories.implementations.user_repository import UserRepository
from app.services.auth_service import AuthService
from shared.cache.redis_client import TokenBlacklist

def get_user_repository(
    db: DBSession,
):
    return UserRepository(db)

def get_token_blacklist() -> TokenBlacklist:
    return TokenBlacklist()

def get_auth_service(user_repository:UserRepository=Depends(get_user_repository),token_blacklist:TokenBlacklist=Depends(get_token_blacklist)) -> AuthService:
    return AuthService(user_repository,token_blacklist)