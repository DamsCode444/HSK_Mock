"""link local users to Clerk identities

Revision ID: e7c3a93f1b24
Revises: 9d1b2f7a4c83
Create Date: 2026-08-31 13:10:00

The link is nullable so every existing local user and attempt keeps its
current primary/foreign key. MySQL permits multiple NULL values in a unique
index, while preventing two local accounts from claiming one Clerk user.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7c3a93f1b24"
down_revision: Union[str, Sequence[str], None] = "9d1b2f7a4c83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_users_clerk_user_id",
        "users",
        ["clerk_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
