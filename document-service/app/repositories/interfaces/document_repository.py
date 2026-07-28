from abc import ABC, abstractmethod
from uuid import UUID
from app.models.document import Document



class IDocumentRepository(ABC):

    @abstractmethod
    async def create(self, document: Document) -> Document:
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Document | None:
        ...

    @abstractmethod
    async def list_by_owner(self, owner_id: UUID) -> list[Document]:
        ...

    @abstractmethod
    async def update(self, document: Document)->Document:
        ...