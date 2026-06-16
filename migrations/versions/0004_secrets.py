"""encrypted secrets store

Revision ID: 0004_secrets
Revises: 0003_multitenancy
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_secrets"
down_revision: Union[str, None] = "0003_multitenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_secrets_workspace_id", "secrets", ["workspace_id"])
    op.create_index("ix_secrets_name", "secrets", ["name"])


def downgrade() -> None:
    op.drop_index("ix_secrets_name", table_name="secrets")
    op.drop_index("ix_secrets_workspace_id", table_name="secrets")
    op.drop_table("secrets")
