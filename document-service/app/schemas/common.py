from uuid import UUID
from datetime import datetime

from shared.schemas.base import BaseSchema

class TimestampSchema(BaseSchema):
    created_at:datetime
    updated_at:datetime

class UUIDSchema(BaseSchema):
    id:UUID

class BaseResponse(UUIDSchema,TimestampSchema):
    pass