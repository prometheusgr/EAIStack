"""Add the versioned workflow store and chat-turn version records

Issue #83 (epic #80 slice 3/5): workflow definitions become runtime-
editable through an admin UI, with Postgres as the system of record.

- workflow_versions: append-only, one row per revision (built-in or admin),
  with a per-workflow sequence and a hash chain for tamper evidence. The
  (workflow_name, sequence) unique constraint stops concurrent saves from
  forking the chain.
- workflow_active_versions: the per-workflow "published" pointer, the only
  mutable table; every move is audit-logged in the same transaction.
- chat_turn_versions: which version answered each chat turn. No FK to
  conversation_threads - it has its own retention window and is expected
  to outlive the conversation.
- system_settings.chat_turn_version_retention_days: that window's DB
  override (NULL = use the env default).

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason as migrations 003-014: the local dev Postgres instance is
shared with Keycloak, so autogenerate's diff also picks up Keycloak's
entire schema as "to be dropped".

Revision ID: 015
Revises: 014
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("yaml_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chain_hash", sa.String(64), nullable=False),
        sa.Column("prev_chain_hash", sa.String(64), nullable=True),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("author_user_id", sa.String(255), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["workflow_versions.id"]),
        sa.UniqueConstraint("workflow_name", "sequence", name="uq_workflow_versions_name_sequence"),
    )
    op.create_index("ix_workflow_versions_workflow_name", "workflow_versions", ["workflow_name"])

    op.create_table(
        "workflow_active_versions",
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("workflow_name"),
        sa.ForeignKeyConstraint(["version_id"], ["workflow_versions.id"]),
    )

    op.create_table(
        "chat_turn_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("workflow_version_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workflow_version_id"], ["workflow_versions.id"]),
    )
    op.create_index("ix_chat_turn_versions_user_id", "chat_turn_versions", ["user_id"])
    op.create_index("ix_chat_turn_versions_thread_id", "chat_turn_versions", ["thread_id"])
    op.create_index("ix_chat_turn_versions_created_at", "chat_turn_versions", ["created_at"])

    op.add_column(
        "system_settings",
        sa.Column("chat_turn_version_retention_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "chat_turn_version_retention_days")
    op.drop_index("ix_chat_turn_versions_created_at", table_name="chat_turn_versions")
    op.drop_index("ix_chat_turn_versions_thread_id", table_name="chat_turn_versions")
    op.drop_index("ix_chat_turn_versions_user_id", table_name="chat_turn_versions")
    op.drop_table("chat_turn_versions")
    op.drop_table("workflow_active_versions")
    op.drop_index("ix_workflow_versions_workflow_name", table_name="workflow_versions")
    op.drop_table("workflow_versions")
