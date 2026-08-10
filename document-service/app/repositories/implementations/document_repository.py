from uuid import UUID

from sqlalchemy import select
from app.repositories.base_repository import BaseRepository

from app.models.document import Document
from app.repositories.interfaces.document_repository import (
    IDocumentRepository,
)


class DocumentRepository(BaseRepository[Document],IDocumentRepository):

    def __init__(self, db):
        super().__init__(db,Document)
    async def list_by_owner(self,owner_id:UUID) -> list[Document]:
        result=await self.db.execute(select(Document).where(Document.owner_id == owner_id,Document.is_deleted.is_(False)).order_by(Document.created_at.desc()))
        return list(result.scalars().all())
    
        

    