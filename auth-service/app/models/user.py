from sqlalchemy import String, Boolean

from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base
from shared.database.mixins import (
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
)


class User(
    Base,
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )