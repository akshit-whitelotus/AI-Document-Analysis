from enum import Enum
from sqlalchemy import String,Integer,Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped,mapped_column

from shared.database.base import Base
from shared.database.mixins import UUIDMixin,TimestampMixin,SoftDeleteMixin

class DocumentStatus(str,Enum):
    PENDING="pending"
    PROCESSING="processing"
    PROCESSED="processed"
    FAILED="failed"

class Document(Base,UUIDMixin,TimestampMixin,SoftDeleteMixin):
    __tablename__ ="documents"

    owner_id:Mapped[str]=mapped_column(PG_UUID(as_uuid=True),index=True,nullable=False)
    filename:Mapped[str]=mapped_column(String(500),nullable=False)
    storage_path:Mapped[str]=mapped_column(String(1000),nullable=False)
    content_path:Mapped[str]=mapped_column(String(100),nullable=False,default="application/pdf")
    status:Mapped[str]=mapped_column(String(20),nullable=False,default=DocumentStatus.PENDING.value)
    error_message:Mapped[str | None]=mapped_column(Text,nullable=True)
    page_count:Mapped[int| None]=mapped_column(Integer,nullable=True)
    chunk_count:Mapped[int | None]=mapped_column(Integer,nullable=True)