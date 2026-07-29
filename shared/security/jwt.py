from datetime import datetime,timedelta,UTC
from typing import Any,Literal
from uuid import UUID

from jose import JWTError,jwt

from shared.config.settings import settings
from shared.exceptions.exceptions import UnauthorizedException

ALGORITHM=settings.JWT_ALGORITHM

def _create_token(subject:str | UUID,expires_delta:timedelta,token_type:Literal["access","refresh"],extra_claims:dict[str,Any] | None=None) -> str :
    now=datetime.now(UTC)
    payload:dict[str,Any] = {
        "sub":str(subject),
        "type":token_type,
        "iat":now,
        "exp":now + expires_delta
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload,settings.JWT_SECRET_KEY,algorithm=ALGORITHM)

def create_access_token(subject:str | UUID , extra_claims:dict[str,Any] | None=None) -> str:
    return _create_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
        extra_claims
    )

def create_refresh_token(subject: str | UUID) -> str :
    return _create_token(subject,timedelta(days=7),"refresh")

def decode_token(token:str,expected_type:Literal["acess","refresh"] | None=None) -> dict[str,Any]:
    try:
        payload=jwt.decode(token,settings.JWT_SECRET_KEY,algorithms=[ALGORITHM])
    except JWTError as exc :
        raise UnauthorizedException("Invalid or expired token") from exc

    if expected_type and payload.get("type") !=expected_type:
        raise UnauthorizedException(f"Expected a {expected_type} token")
    return payload
