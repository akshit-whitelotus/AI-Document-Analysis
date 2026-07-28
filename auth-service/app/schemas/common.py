from uuid import UUID
from datetime import datetime

from pydantic import ConfigDict

from shared.schemas.base import BaseSchema


class TimestampSchema(BaseSchema):
    created_at: datetime
    updated_at: datetime


class UUIDSchema(BaseSchema):
    id: UUID


class BaseResponse(UUIDSchema, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)