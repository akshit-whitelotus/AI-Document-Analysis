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
    async def get_by_username(self,username:str):
        result=await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    async def exists_by_username(self,username:str):
        return await self.get_by_username(username) is not None

    async def update_role(self,user:User,role):
        user.role = role
        await self.db.commit()
        await self.db.refresh(user)
        return user