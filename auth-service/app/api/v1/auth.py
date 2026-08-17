from typing import Annotated
from uuid import UUID
from fastapi import APIRouter ,Depends,status
from shared.exceptions.exceptions import UnauthorizedException
from shared.security.oauth import AdminUserDep,CurrentUserDep

from app.dependencies.repository import get_auth_service
from app.schemas.auth import RefreshTokenRequest
from app.schemas.token import Token
from app.schemas.user import RoleUpdateRequest,UserCreate,UserLogin,UserResponse
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

@router.post("/logout",status_code=status.HTTP_204_NO_CONTENT)
async def logout(data:RefreshTokenRequest,auth_service:AuthServiceDep):
    """
    Revokes the given refresh token (see AuthService.logout /
    TokenBlacklist) so it can't be used again to mint new access tokens.
    Takes the refresh token in the body rather than requiring the access
    token as auth, mirroring /refresh - possessing a valid, unexpired
    refresh token is itself proof of ownership.
    """
    await auth_service.logout(data.refresh_token)

@router.get("/me",response_model=UserResponse)
async def me(current_user:CurrentUserDep,auth_service:AuthServiceDep):
    user=await auth_service.user_repository.get_by_id(current_user.id)
    if not user:
        raise UnauthorizedException("User no longer exists")
    return user

@router.get("/users",response_model=list[UserResponse])
async def list_users(admin_user:AdminUserDep,auth_service:AuthServiceDep):
    """
    Admin-only. Lists every registered account (including disabled ones- 
    is_active is part of UserResponse, so an admin can tell disabled users
    apart from active ones in the same list rather than needing a second
    endpoint). Same AdminUserDep guard as the role-update route below.
    """
    return await auth_service.user_repository.list_all()
@router.patch("/users/{user_id}/role",response_model=UserResponse)
async def update_user_role(
    user_id:UUID,
    data:RoleUpdateRequest,
    admin_user:AdminUserDep,
    auth_service:AuthServiceDep,
):
    """
    Admin-only. Promotes or demotes a user's role. Guarded by AdminUserDep
    (shared.security.oauth.require_role("admin")) - the caller's own JWT
    must already carry role="admin", which is only ever set here or
    directly in the database, never via self-registration.
    """
    return await auth_service.set_role(user_id,data.role)

