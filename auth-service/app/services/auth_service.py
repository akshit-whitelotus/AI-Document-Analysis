from shared.exceptions.exceptions import UnauthorizedException,ValidationException,NotFoundException
from shared.security.hashing import hash_password,verify_password
from shared.security.jwt import create_access_token,create_refresh_token,decode_token,remaining_ttl_seconds
from shared.cache.redis_client import TokenBlacklist

from app.models.user import User,Role
from app.repositories.implementations.user_repository import UserRepository
from app.schemas.token import Token
from app.schemas.user import UserCreate,UserLogin

class AuthService:
    def __init__(self,user_repository:UserRepository,token_blacklist:TokenBlacklist | None=None):
        self.user_repository = user_repository
        self.token_blacklist = token_blacklist or TokenBlacklist()

    async def register(self, data:UserCreate) -> User:
        if await self.user_repository.exists_by_email(data.email):
            raise ValidationException("A user with this email already exists")
        if await self.user_repository.exists_by_username(data.username):
            raise ValidationException("A user with this username already exists")
        user=User(
            first_name=data.first_name,
            last_name=data.last_name,
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            role=Role.USER,
        )
        return await self.user_repository.create(user)
    async def set_role(self,user_id,role:Role) -> User:
        """
        Admin-only promotion/demotion path (see require_role("admin) guard
        on the route). Never reachable from self-registration -role is
        fixed to ROle.USER there.
        """
        user=await self.user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        return await self.user_repository.update_role(user,role)

    async def login(self,data:UserLogin) -> Token:
        user = await self.user_repository.get_by_email(data.email)
        if not user or not verify_password(data.password,user.password_hash):
            raise UnauthorizedException("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedException("The account is disabled")
        return self._issue_tokens(user)
    async def refresh(self,refresh_token:str) -> Token:
        """
        Rotates on every use: the presented refresh token is immediately
        blacklisted and a brand new access/refresh pair is issued. A caller
        that tries to reuse the same refresh token again (e.g because it
        leaked, or two tabs raced) gets UnauthorizedException on the second
        attempt - single-use tokens mean a stolen-but-already-used refresh
        token is worthless to an attacker.
        """
        payload=decode_token(refresh_token,expected_type="refresh")
        if await self.token_blacklist.is_revoked(payload["jti"]):
            raise UnauthorizedException("This refresh token has already been used or revoked")
        user=await self.user_repository.get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise UnauthorizedException("Invalid refresh token")
        await self.token_blacklist.revoke(payload["jti"],remaining_ttl_seconds(payload))
        return self._issue_tokens(user)
    async def logout(self,refresh_token:str) -> None:
        """
        Blacklists the given refresh token so it can no longer can be used to 
        obtain new access tokens. Delibaretely does NOT also blacklist the 
        caller's current access token: access tokens are short-lived (see
        ACCESS_TOKEN_EXPIRE_MINUTES) and checking a blacklist on every
        single request across every service would means a Redis rond trip 
        per request - not worth it for a token that expires in minutes 
        anyway. THe refresh token is the one that matters, since it's what
        lets someone stay logged in for days.
        """
        payload = decode_token(refresh_token,expected_type="refresh")
        await self.token_blacklist.revoke(payload["jti"],remaining_ttl_seconds(payload))

    @staticmethod
    def _issue_tokens(user:User) -> Token:
        extra_claims={"email":user.email,"role":user.role}
        return Token (
            access_token=create_access_token(user.id,extra_claims=extra_claims),
            refresh_token=create_refresh_token(user.id)
        )