"""SQLAlchemy models for database schema."""

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utc_now() -> datetime:
    """Get current UTC time. Uses timezone-aware datetime for compatibility with Python 3.12+."""
    return datetime.now(timezone.utc)


class ProviderEnum(str, enum.Enum):
    """Supported API key providers."""

    openai = "openai"
    anthropic = "anthropic"
    huggingface = "huggingface"
    custom = "custom"


class APIKey(Base):
    """API Key model for storing user credentials."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Store as string: openai, anthropic, huggingface, custom
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    secret_value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def __repr__(self):
        return f"<APIKey(id={self.id}, name={self.name}, provider={self.provider}, user_id={self.user_id})>"


class KnowledgeBase(Base):
    """Knowledge Base entry model for storing documents."""

    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    embeddings = relationship("Embedding", back_populates="knowledge_base")

    def __repr__(self):
        return f"<KnowledgeBase(id={self.id}, user_id={self.user_id}, title={self.title})>"


class Embedding(Base):
    """Embedding model for storing vector embeddings."""

    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    embed_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    knowledge_base = relationship("KnowledgeBase", back_populates="embeddings")

    def __repr__(self):
        return f"<Embedding(id={self.id}, doc_id={self.doc_id})>"


class ConversationThread(Base):
    """Ownership record for one chat conversation.

    This table's id doubles as the LangGraph thread_id. It exists
    separately from ConversationCheckpoint so that authorization
    (does this thread belong to this user?) can be checked without
    ever touching checkpoint state, and so ThreadRepository is the
    single structural place that check happens - no endpoint or
    agent code may resolve a thread_id to state without going
    through it first.
    """

    __tablename__ = "conversation_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    def __repr__(self):
        return f"<ConversationThread(id={self.id}, user_id={self.user_id})>"


class ConversationCheckpoint(Base):
    """Latest LangGraph checkpoint state for one conversation thread.

    Stores only the most recent checkpoint per thread (upserted), not
    full checkpoint history - Phase 4a's scope is resuming a
    conversation, not time-travel/replay. No user_id column: isolation
    is enforced one layer up by ThreadRepository, the same way Embedding
    has no user_id and is only ever reached through KnowledgeBase.

    checkpoint/checkpoint_metadata are opaque serialized bytes (msgpack,
    via LangGraph's own JsonPlusSerializer - see
    app.agents.checkpointer.SqlAlchemyCheckpointSaver) rather than JSON
    columns: LangGraph checkpoints contain LangChain message objects and
    other non-JSON-native types that the serializer already knows how to
    encode, so this table stores its output as-is instead of duplicating
    that logic.
    """

    __tablename__ = "conversation_checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    checkpoint_metadata: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    def __repr__(self):
        return f"<ConversationCheckpoint(id={self.id}, thread_id={self.thread_id})>"


class SystemSettings(Base):
    """Singleton row holding runtime-mutable LLM/embedding provider config.

    Exactly one row is expected to exist (id="default"). Unlike other models
    here, this is deliberately NOT user-scoped — it's a system-wide setting,
    not per-tenant data — so it has no user_id and the repository pattern's
    usual per-user filtering does not apply.
    """

    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self):
        return f"<SystemSettings(id={self.id}, llm_provider={self.llm_provider}, embedding_provider={self.embedding_provider})>"
