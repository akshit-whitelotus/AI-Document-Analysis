from shared.exceptions.exceptions import UnauthorizedException,ValidationException
from shared.security.hashing import hash_password,verify_password
from shared.security.jwt import create_access_token,create_refresh_token,decode_token

from app.models.user import User
from app.repositories.implementations.user_repository import UserRepository
from app.schemas.token import Token
from app.schemas.user import UserCreate,UserLogin

class AuthService:
    def __init__(self,user_repository:UserRepository):
        self.user_repository = user_repository

    async def register(self, data:UserCreate) -> User:
        if await self.user_repository.exists_by_email(data.email):
            raise ValidationException("A user with this email already exists")
        if await self.user_repository.exists_by_username(data.username):
            raise ValidationException("A user with this username already exists")
        if data.doc_id and await self.user_repository.exists_by_doc_id(data.doc_id):
            raise ValidationException("This doc_id is already linked to another user")
        user=User(
            first_name=data.first_name,
            last_name=data.last_name,
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            role=data.role,
            doc_id=data.doc_id,
            doc_type=data.doc_type,
        )
        return await self.user_repository.create(user)
    async def login(self,data:UserLogin) -> Token:
        user = await self.user_repository.get_by_email(data.email)
        if not user or not verify_password(data.password,user.password_hash):
            raise UnauthorizedException("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedException("The account is disabled")
        return self._issue_tokens(user)
    async def refresh(self,refresh_token:str) -> Token:
        payload=decode_token(refresh_token,expected_type="refresh")
        user=await self.user_repository.get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise UnauthorizedException("Invalied refresh token")

        return self._issue_tokens(user)

    @staticmethod
    def _issue_tokens(user:User) -> Token:
        extra_claims={"email":user.email,"role":user.role}
        return Token (
            access_token=create_access_token(user.id,extra_claims=extra_claims),
            refresh_token=create_refresh_token(user.id)
        )