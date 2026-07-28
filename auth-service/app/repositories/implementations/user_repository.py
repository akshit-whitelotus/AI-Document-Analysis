from sqlalchemy import select

from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.repositories.interfaces.user_repository import IUserRepository


class UserRepository(
    BaseRepository[User],
    IUserRepository,
):

    def __init__(self, db):
        super().__init__(db, User)

    async def get_by_email(self, email: str):
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def exists_by_email(self, email: str):
        return await self.get_by_email(email) is not None