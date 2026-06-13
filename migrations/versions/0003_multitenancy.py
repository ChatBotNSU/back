"""multitenancy: workspace_id on flows + bots

Revision ID: 0003_multitenancy
Revises: 0002_flow_versions
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_multitenancy"
down_revision: Union[str, None] = "0002_flow_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("flows", "bots"):
        op.add_column(
            table,
            sa.Column("workspace_id", sa.String(), nullable=False, server_default="default"),
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade() -> None:
    for table in ("flows", "bots"):
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
