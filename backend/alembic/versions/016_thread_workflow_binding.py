"""Bind each conversation thread to a workflow

Issue #85 (epic #80 slice 5/5): a user picks a workflow when starting a
conversation, and every later turn runs that workflow. Existing threads
predate the choice and were all answered by the default chat workflow, so
the server default backfills them as "chat".

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason as migrations 003-015: the local dev Postgres instance is shared
with Keycloak, so autogenerate's diff also picks up Keycloak's schema.

Revision ID: 016
Revises: 015
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("workflow_name", sa.String(255), nullable=False, server_default="chat"),
    )


def downgrade() -> None:
    op.drop_column("conversation_threads", "workflow_name")
