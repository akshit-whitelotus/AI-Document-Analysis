from pydantic import EmailStr, Field

from .common import BaseResponse
from shared.schemas.base import BaseSchema


class UserCreate(BaseSchema):
    full_name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class UserLogin(BaseSchema):
    email: EmailStr
    password: str


class UserResponse(BaseResponse):
    full_name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool