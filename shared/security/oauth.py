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

def get_current_user(credentials:Annotated[HTTPAuthorizationCredentials,Depends(oauth_scheme)]) -> CurrentUser:
    payload=decode_token(credentials.credentials,expected_type="access")
    sub=payload.get("sub")
    if not sub:
        raise UnauthorizedException("Token missing subject claim")
    return CurrentUser(id=UUID(sub),raw_claims=payload)

CurrentUserDep=Annotated[CurrentUser,Depends(get_current_user)]