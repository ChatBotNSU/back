"""users (auth)

Revision ID: 0008_users
Revises: 0007_integrations
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_users"
down_revision: Union[str, None] = "0007_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
