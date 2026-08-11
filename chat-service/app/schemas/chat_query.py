from shared.schemas.base import BaseSchema

class ChatQueryRequest(BaseSchema):
    session_id:str
    question:str
    top_k: int=5
    document_ids: list[str] | None = None

class SourceChunk(BaseSchema):
    document_id:str
    chunk_index:int
    text:str
    score:float

class ChatQueryResponse(BaseSchema):
    answer:str
    sources:list[SourceChunk]
    cached:bool=False

class SessionDocumentRequest(BaseSchema):
    """Sets the persistent set of documents a session's queries are scoped 
    to, so document_ids doesn't need to be a repeated on every /query call."""
    document_ids:list[str]

class SessionDocumentResponse(BaseSchema):
    session_id:str
    document_ids:list[str]