from datetime import datetime,UTC
from uuid import uuid4
from app.models.document import Document

class FakeDocumentRepository:
    def __init__(self):
        self._by_id: dict = {}
    async def create(self, document:Document) -> Document :
        if document.id is None:
            document.id = uuid4()
        now = datetime.now(UTC)
        document.created_at = now
        document.updated_at = now
        if document.is_deleted is None :
            document.is_deleted = False
        self._by_id[document.id] = document
        return document
    async def get_by_id(self, id):
        return self._by_id.get(id)

    async def update(self, document:Document) -> Document:
        document.updated_at = datetime.now(UTC)
        self._by_id[document.id] = document
        return document
    async def list_by_owner(self,owner_id) -> list[Document]:
        return[
            d for d in self._by_id.values()
            if d.owner_id == owner_id and not d.is_deleted
        ]
    