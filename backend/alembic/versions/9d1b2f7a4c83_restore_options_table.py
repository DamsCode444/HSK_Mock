"""restore the question options table when upgrading an early local database

Revision ID: 9d1b2f7a4c83
Revises: fb391440fdef
Create Date: 2026-08-31 00:00:00

The initial migration already creates this table for new installations.  A
small number of Phase 1 development databases were created before that step
completed, so this forward migration deliberately checks the live schema and
only repairs the table when it is absent.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d1b2f7a4c83"
down_revision: Union[str, Sequence[str], None] = "fb391440fdef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "options" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "options",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "label", name="uq_options_question_label"),
    )
    op.create_index(op.f("ix_options_question_id"), "options", ["question_id"])


def downgrade() -> None:
    # The options table belongs to the initial schema, so reversing this repair
    # must not remove it.
    pass
