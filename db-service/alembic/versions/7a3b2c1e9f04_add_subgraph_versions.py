"""add subgraph versions

Revision ID: 7a3b2c1e9f04
Revises: 5f6d9c8e7a12
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a3b2c1e9f04"
down_revision: Union[str, Sequence[str], None] = "5f6d9c8e7a12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "subgraph_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("subgraph_name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PUBLISHED",
                "ARCHIVED",
                name="versionstatusenum",
                native_enum=False,
                create_constraint=False,  # already created by chatbot_versions migration
            ),
            nullable=False,
        ),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["subgraph_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key"),
    )
    # Hot-path index: lookup latest version of a subgraph for a given user.
    op.create_index(
        "ix_subgraph_versions_owner_name_created",
        "subgraph_versions",
        ["owner_user_id", "subgraph_name", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_subgraph_versions_owner_name_created", table_name="subgraph_versions")
    op.drop_table("subgraph_versions")
