"""project integrations

Revision ID: 0007_integrations
Revises: 0006_data_records
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_integrations"
down_revision: Union[str, None] = "0006_data_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="provider"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_project_id", "integrations", ["project_id"])
    op.create_index("ix_integrations_name", "integrations", ["name"])


def downgrade() -> None:
    op.drop_index("ix_integrations_name", table_name="integrations")
    op.drop_index("ix_integrations_project_id", table_name="integrations")
    op.drop_table("integrations")
