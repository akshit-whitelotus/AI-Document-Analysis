from datetime import datetime,UTC
from uuid import UUID,uuid4

from app.models.user import User

class FakeUserRepository:
    def __init__(self):
        self._by_id: dict={}
    async def create(self,user:User) -> User:
        if user.id is None:
            user.id = uuid4()
        now=datetime.now(UTC)
        user.created_at = now
        user.updated_at = now
        if user.is_active is None:
            user.is_active = True
        if user.is_deleted is None:
            user.is_deleted =False
        self._by_id[user.id] = user
        return user
    async def get_by_id(self,id):
        return self._by_id.get(id if isinstance(id,UUID) else UUID(str(id)))
    async def get_by_email(self,email:str):
        return next((u for u in self._by_id.values() if u.email == email),None)

    async def exists_by_email(self,email:str) -> bool :
        return any(u.email == email for u in self._by_id.values())
    async def get_by_username(self,username:str):
        return next((u for u in self._by_id.values() if u.username == username), None)
    async def exists_by_username(self,username:str) -> bool:
        return any(u.username == username for u in self._by_id.values())
    