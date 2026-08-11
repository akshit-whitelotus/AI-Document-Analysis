from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from shared.exceptions.exceptions import UnauthorizedException,ForbiddenException
from shared.security.jwt import decode_token

oauth_scheme=HTTPBearer(auto_error=True)

class CurrentUser(BaseModel):
    id:UUID
    role:str | None=None
    raw_claims:dict

def resolve_user_from_token(token:str) -> CurrentUser:
    """
    Shared by both get_current_user() (HTTP, via the Authorization header)
    and WebSocket routes (which authenticate via a ?token= query param
    instead, since browsers' native WebSocket API can't set custom
    headers like Authorization) - same validation, same CurrentUser shape,
    just a different place the raw token string comes from.
    """
    payload=decode_token(token,expected_type="access")
    sub=payload.get("sub")
    if not sub:
        raise UnauthorizedException("Token missing subject claim")
    return CurrentUser(id=UUID(sub),role=payload.get("role"),raw_claims=payload)

def get_current_user(credentials:Annotated[HTTPAuthorizationCredentials,Depends(oauth_scheme)]) -> CurrentUser:
    return resolve_user_from_token(credentials.credentials)

CurrentUserDep=Annotated[CurrentUser,Depends(get_current_user)]

def require_role(*allowed_roles:str):
    """
    Route-guard dependency factory. `role` is trusted straight from the
    JWT claim (set once, server-side, at issuance time in 
    auth_service._issue_tokens - see auth_service.py) so this never needs 
    a DB round trip. Usage: `Depends(require_role("admin"))` or via the
    AdminUserDep alias below.
    """
    def _check(current_user:CurrentUserDep) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise ForbiddenException("You do not have permission to perform this action")
        return current_user
    return _check

AdminUserDep=Annotated[CurrentUser,Depends(require_role("admin"))]