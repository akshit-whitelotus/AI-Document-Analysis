"""remove doc_id and doc_type from users

doc_id/doc_type (added in 002) turned out to be an unrelated, confusing 
requirement bolted onto user registration - it had nothing to do with the
actual `documents` table owned by document-service, and no code outside
of auth-service's registration  path ever read it. Removing it entirely
rather than just making it optional, since nothing depends on it

Revision ID: 003
Revises: 002
Create Date: 2026-08-11 00:00:00.000000


"""
from typing import Sequence,Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision:str = "003"
down_revision:Union[str,Sequence[str],None] = "002"
branch_labels:Union[str,Sequence[str],None] = None
depends_on:Union[str,Sequence[str],None]=None

doc_type_enum=postgresql.ENUM("pdf","txt",name="doc_type")

def upgrade() -> None:
    bind=op.get_bind()
    op.drop_index(op.f("ix_users_doc_id"),table_name="users")
    op.drop_column("users","doc_type")
    op.drop_column("users","doc_id")
    doc_type_enum.drop(bind,checkfirst=True)

def downgrade() -> None:
    bind = op.get_bind()
    doc_type_enum.create(bind,checkfirst=True)
    op.add_column("users",sa.Column("doc_id",sa.String(),nullable=True))
    op.add_column("users",sa.Column("doc_type",doc_type_enum,nullable=True))
    op.create_index(op.f("ix_users_doc_id"),"users",["doc_id"],unique=True)
    