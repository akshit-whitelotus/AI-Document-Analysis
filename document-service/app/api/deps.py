from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_db
from shared.security.oauth import CurrentUserDep

DBSession=Annotated[AsyncSession,Depends(get_db)]

__all__=["DBSession","CurrentUserDep"]