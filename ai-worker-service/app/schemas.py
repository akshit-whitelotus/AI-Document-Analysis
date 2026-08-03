from shared.schemas.base import BaseSchema

class SearchRequest(BaseSchema):
    query:str
    top_k: int = 5
    owner_id:str
    document_ids: list[str] | None = None

class SearchResultItem(BaseSchema):
    document_id:str
    chunk_index:int
    text:str
    score:float

class SearchResponse(BaseSchema):
    results:list[SearchResultItem]