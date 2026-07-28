from abc import ABC, abstractmethod

from app.models.user import User


class IUserRepository(ABC):

    @abstractmethod
    async def create(self, user: User):
        ...

    @abstractmethod
    async def get_by_email(self, email: str):
        ...

    @abstractmethod
    async def exists_by_email(self, email: str):
        ...