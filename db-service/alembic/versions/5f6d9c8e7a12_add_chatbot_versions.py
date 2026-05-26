"""add chatbot versions

Revision ID: 5f6d9c8e7a12
Revises: b3b0e50b4b6d
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f6d9c8e7a12"
down_revision: Union[str, Sequence[str], None] = "b3b0e50b4b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chatbot_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), nullable=False),
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
            ),
            nullable=False,
        ),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chat_bots.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["chatbot_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("chatbot_versions")
