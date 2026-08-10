from pydantic import EmailStr, Field

from .common import BaseResponse
from shared.schemas.base import BaseSchema
from app.models.user import Role,DocType


class UserCreate(BaseSchema):
    first_name: str = Field(min_length=2,max_length=100,)
    last_name: str = Field(min_length=2,max_length=100,)
    username: str = Field(min_length=2,max_length=100,)
    role:Role=Field(default=Role.USER)
    email: EmailStr
    password: str = Field(min_length=8,max_length=128,)
    doc_id:str=Field(min_length=2,max_length=100)
    doc_type:DocType


class UserLogin(BaseSchema):
    email: EmailStr
    password: str


class UserResponse(BaseResponse):
    first_name: str
    last_name: str
    username:str
    email: EmailStr
    is_active: bool
    role:Role
    doc_id:str | None = None
    doc_type:DocType | None=None

    