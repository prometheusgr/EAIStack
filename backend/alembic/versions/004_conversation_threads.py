"""Add conversation_threads and conversation_checkpoints tables

Adds the tables backing Phase 4a's conversation persistence: a
ConversationThread row per chat thread (the ownership/authorization
record, keyed by user_id) and a ConversationCheckpoint row holding the
latest LangGraph checkpoint state for that thread (see
app.agents.checkpointer.SqlAlchemyCheckpointSaver and
app.repositories.thread_repository.ThreadRepository).

Two tables rather than one because thread ownership and checkpoint
payload have different lifecycles/access patterns: listing a user's
threads (GET /api/agents/threads) only ever needs
conversation_threads; only resuming a chat needs the checkpoint
payload too. conversation_checkpoints has no user_id column by
design - ownership is enforced structurally through
ThreadRepository before a thread_id is ever used to read or write a
checkpoint, the same way Embedding has no user_id and is only
reachable through KnowledgeBase.

checkpoint/checkpoint_metadata are stored as opaque bytes (LangGraph's
own msgpack serialization via JsonPlusSerializer), not JSON columns -
checkpoints contain LangChain message objects and other types that
aren't natively JSON-serializable.

Revision ID: 004
Revises: 003
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_threads_user_id", "conversation_threads", ["user_id"])

    op.create_table(
        "conversation_checkpoints",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("checkpoint", sa.LargeBinary(), nullable=False),
        sa.Column("checkpoint_metadata", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_checkpoints_thread_id",
        "conversation_checkpoints",
        ["thread_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_checkpoints_thread_id", table_name="conversation_checkpoints")
    op.drop_table("conversation_checkpoints")
    op.drop_index("ix_conversation_threads_user_id", table_name="conversation_threads")
    op.drop_table("conversation_threads")
