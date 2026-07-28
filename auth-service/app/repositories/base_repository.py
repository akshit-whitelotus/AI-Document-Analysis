from typing import Generic, TypeVar, Type
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(
        self,
        db: AsyncSession,
        model: Type[T],
    ):
        self.db = db
        self.model = model

    async def get_by_id(self, id: UUID):
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def create(self, obj: T):
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: T):
        await self.db.delete(obj)
        await self.db.commit()

    async def list_all(self):
        result = await self.db.execute(select(self.model))
        return result.scalars().all()