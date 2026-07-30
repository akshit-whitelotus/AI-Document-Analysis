from typing import Sequence,Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision:str ="002"
down_revision:Union[str,Sequence[str],None] = "81e22cc241d2"
branch_labels: Union[str,Sequence[str],None]=None
depends_on:Union[str,Sequence[str],None]=None

user_role_enum=postgresql.ENUM("user","admin",name="user_role")
doc_type_enum=postgresql.ENUM("pdf","txt",name="doc_type")

def upgrade() -> None :
    bind = op.get_bind()

    user_role_enum.create(bind,checkfirst=True)
    doc_type_enum.create(bind,checkfirst=True)

    op.add_column("users",sa.Column("first_name",sa.String(length=255),nullable=True))
    op.add_column("users",sa.Column("last_name",sa.String(length=255),nullable=True))
    op.add_column("users",sa.Column("username",sa.String(length=255),nullable=True))
    op.add_column(
        "users",
        sa.Column("role",user_role_enum,nullable=False,server_default="user"))
    op.add_column("users",sa.Column("doc_id",sa.String(),nullable=True))
    op.add_column("users",sa.Column("doc_type",doc_type_enum,nullable=True))
    op.execute(
        """
        UPDATE users
        SET 
            first_name=COALESCE(NULLIF(split_part(full_name,' ',1), ' '),'Unknown'),
            last_name=CASE
                WHEN position(' ' in full_name) > 0
                        THEN trim(substring(full_name from position(' ' in full_name) + 1))
                    ELSE 'User'
            END
        WHERE first_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE users
        SET username = split_part(email, '@', 1)
        WHERE username IS NULL
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,username,
                    ROW_NUMBER() OVER (PARTITION BY username ORDER BY created_at) AS rn
            FROM users
        )
        UPDATE users u
        SET username = u.username || '_' || substr(u.id::text,1,8)
        from ranked r
        where u.id = r.id AND r.rn > 1
        """
    )
    op.alter_column("users","first_name",nullable=False)
    op.alter_column("users","last_name",nullable=False)
    op.alter_column("users","username",nullable=False)
    op.create_index(op.f("ix_users_username"),"users",["username"],unique=True)
    op.create_index(op.f("ix_users_role"),"users",["role"],unique=False)
    op.create_index(op.f("ix_users_doc_id"),"users",["doc_id"],unique=True)

    op.drop_column("users","full_name")
    op.drop_column("users","is_superuser")

def downgrade() -> None:
    bind=op.get_bind()
    op.add_column("users",sa.Column("full_name",sa.String(length=255),nullable=True))
    op.add_column("users",sa.Column("is_superuser",sa.String(length=255),nullable=True))
    op.execute(
        """
        UPDATE users
        SET full_name = trim(first_name || ' ' || last_name),
                is_superuser =(role = 'admin')
        """

    )
    op.alter_column("users","full_name",nullable=False)
    op.alter_column("users","is_superuser",nullable=False,server_default=sa.text("false"))
    op.drop_index(op.f("ix_users_doc_id"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_column("users", "doc_type")
    op.drop_column("users", "doc_id")
    op.drop_column("users", "role")
    op.drop_column("users", "username")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    doc_type_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)

