from shared.schemas.base import BaseSchema

class ChatQueryRequest(BaseSchema):
    session_id:str
    question:str
    top_k: int=5

class SourceChunk(BaseSchema):
    document_id:str
    chunk_index:int
    text:str
    score:float

class ChatQueryResponse(BaseSchema):
    answer:str
    sources:list[SourceChunk]
    cached:bool=False
    