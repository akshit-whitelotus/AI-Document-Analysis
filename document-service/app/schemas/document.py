from uuid import UUID
from shared.schemas.base import BaseSchema
from app.schemas.common import BaseResponse

class DocumentResponse(BaseResponse):
    filename:str
    content_type:str
    status:str
    error_message:str | None=None
    page_count:int | None=None
    chunk_count:int |None=None

class DocumentUploadResponse(BaseSchema):
    id:UUID
    filename:str
    status:str
    message:str = "Docuement accepted, processing has been queued"




