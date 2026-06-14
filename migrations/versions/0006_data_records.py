"""built-in data tables (data_records)

Revision ID: 0006_data_records
Revises: 0005_projects
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_data_records"
down_revision: Union[str, None] = "0005_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("table", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_records_project_id", "data_records", ["project_id"])
    op.create_index("ix_data_records_table", "data_records", ["table"])


def downgrade() -> None:
    op.drop_index("ix_data_records_table", table_name="data_records")
    op.drop_index("ix_data_records_project_id", table_name="data_records")
    op.drop_table("data_records")
