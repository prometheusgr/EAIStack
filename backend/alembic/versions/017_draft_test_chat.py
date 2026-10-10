"""Draft test chat: test-thread binding and test-run marker

Issue #84 slice A (epic #80): an admin can run any saved workflow version
in a test chat. conversation_threads.test_version_id binds such a thread to
the version it runs (NULL for every production conversation, including all
existing rows), and chat_turn_versions.is_test_run marks its turns, since
that record outlives the thread.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason as migrations 003-016: the local dev Postgres instance is shared
with Keycloak, so autogenerate's diff also picks up Keycloak's schema.

Revision ID: 017
Revises: 016
Create Date: 2026-10-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column(
            "test_version_id",
            sa.String(36),
            sa.ForeignKey("workflow_versions.id", name="fk_conversation_threads_test_version_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "chat_turn_versions",
        sa.Column("is_test_run", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_turn_versions", "is_test_run")
    op.drop_constraint(
        "fk_conversation_threads_test_version_id", "conversation_threads", type_="foreignkey"
    )
    op.drop_column("conversation_threads", "test_version_id")
