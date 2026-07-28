from typing import Annotated
from fastapi import APIRouter ,Depends,status
from shared.exceptions.exceptions import UnauthorizedException
from shared.security.oauth import CurrentUserDep

from app.dependencies.repository import get_auth_service
from app.schemas.auth import RefreshTokenRequest
from app.schemas.token import Token
from app.schemas.user import UserCreate,UserLogin,UserResponse
from app.services.auth_service import AuthService

router=APIRouter()

AuthServiceDep=Annotated[AuthService,Depends(get_auth_service)]

@router.post("/register",response_model=UserResponse,status_code=status.HTTP_201_CREATED)
async def register(data:UserCreate,auth_service:AuthServiceDep):
    user=await auth_service.register(data)
    return user

@router.post("/login",response_model=Token)
async def login(data:UserLogin,auth_service:AuthServiceDep):
    return await auth_service.login(data)

@router.post("/refresh",response_model=Token)
async def refresh(data:RefreshTokenRequest,auth_service:AuthServiceDep):
    return await auth_service.refresh(data.refresh_token)

@router.get("/me",response_model=UserResponse)
async def me(current_user:CurrentUserDep,auth_service:AuthServiceDep):
    user=await auth_service.user_repository.get_by_id(current_user.id)
    if not user:
        raise UnauthorizedException("User no longer exists")
    return user

