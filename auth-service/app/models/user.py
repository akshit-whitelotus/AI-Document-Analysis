from sqlalchemy import String, Boolean,Enum
import enum

from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base
from shared.database.mixins import (
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
)

class Role(str,enum.Enum):
    USER="user"
    ADMIN="admin"

class DocType(str,enum.Enum):
    PDF="pdf"
    TXT="txt"

class User(Base,UUIDMixin,TimestampMixin,SoftDeleteMixin,):
    __tablename__ = "users"
    first_name: Mapped[str] = mapped_column(String(255),nullable=False,)
    last_name: Mapped[str] = mapped_column(String(255),nullable=False,)
    username: Mapped[str] = mapped_column(String(255),nullable=False,unique=True,index=True)
    email: Mapped[str] = mapped_column(String(255),unique=True,index=True,nullable=False,)
    password_hash: Mapped[str] = mapped_column(String(255),nullable=False,)
    is_active: Mapped[bool] = mapped_column(Boolean,default=True,)
    role:Mapped[Role]=mapped_column(Enum(Role,name="user_role",values_callable=lambda enum_cls: [e.value for e in enum_cls]),
                                   nullable=False,default=Role.USER,server_default=Role.USER.value,index=True)


    