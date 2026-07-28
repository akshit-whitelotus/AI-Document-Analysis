from shared.schemas.base import BaseSchema

class SearchRequest(BaseSchema):
    query:str
    top_k: int = 5

class SearchResultItem(BaseSchema):
    document_id:str
    chunk_index:int
    text:str
    score:float

class SearchResponse(BaseSchema):
    results:list[SearchResultItem]