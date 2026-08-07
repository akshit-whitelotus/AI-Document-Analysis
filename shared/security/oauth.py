from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from shared.exceptions.exceptions import UnauthorizedException
from shared.security.jwt import decode_token

oauth_scheme=HTTPBearer(auto_error=True)

class CurrentUser(BaseModel):
    id:UUID
    raw_claims:dict

def resolve_user_from_token(token:str) -> CurrentUser:
    """
        Shared by both get_current_user() (HTTP, via the Authorization header)
        and WebSocket routes (which authenticate via a ?token= query param
        instead, since browsers' native WebSocket API can't set custom
        headers like Authorization) - same validation, same CurrentUser shape,
        just a different place the raw token string comes from.
    """
    payload = decode_token(token,expected_type="access")
    sub=payload.get("sub")
    if not sub:
        raise UnauthorizedException("Token missing subject claim")
    return CurrentUser(id=UUID(sub),raw_claims=payload)

def get_current_user(credentials:Annotated[HTTPAuthorizationCredentials,Depends(oauth_scheme)]) -> CurrentUser:
    payload=decode_token(credentials.credentials,expected_type="access")
    sub=payload.get("sub")
    if not sub:
        raise UnauthorizedException("Token missing subject claim")
    return CurrentUser(id=UUID(sub),raw_claims=payload)

CurrentUserDep=Annotated[CurrentUser,Depends(get_current_user)]