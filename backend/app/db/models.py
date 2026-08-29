"""SQLAlchemy models for database schema."""

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
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
    """Knowledge Base entry model for storing documents.

    `content` always holds extracted, searchable text - for a pasted-text
    entry that's the text itself; for an uploaded file it's the result of
    app.storage.text_extraction run against the original bytes. Keeping
    extracted text in Postgres (rather than only in MinIO) is a deliberate
    choice: it is what embeddings and search actually operate on, so every
    read path continues to work unchanged for uploaded documents.

    storage_key/original_filename/content_type are populated only for
    file-backed entries and are NULL (not empty string) for typed entries -
    the distinguishing signal an endpoint uses to know whether a MinIO
    object exists to serve back or purge. storage_key is a MinIO object
    path scoped as f"{user_id}/{kb_id}/{filename}" (see
    app.storage.object_keys) - callers must build it that way rather than
    trusting a client-supplied key, since a path under the wrong prefix
    would defeat the per-user bucket isolation this column exists to record.
    """

    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    """Embedding model for storing vector embeddings.

    One row per chunk, not per document (see
    backend/app/services/chunking_service.py): a document is split into
    passage-sized chunks before embedding, so several Embedding rows
    typically share one doc_id. chunk_index/chunk_text/heading_path were
    added for this; a row predating chunking still has exactly one chunk
    (chunk_index=0, heading_path=NULL) and continues to work unchanged,
    since chunking is applied only on the next create/update of its
    KnowledgeBase, not backfilled (see the migration's own docstring for why).
    """

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
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    heading_path: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
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


class AuditLog(Base):
    """Append-only record of a security-relevant configuration change.

    The first audit record in the system, introduced with Phase 4b's
    retention settings. Deliberately append-only: no application code
    updates or deletes a row, and every retention purge path is
    structurally incapable of touching this table (see
    app.services.retention_service and docs/SECURITY.md's retention
    policy table). Audit history is retained on an independent schedule
    from session/conversation data, so a shortened conversation window
    must never erase the record of who shortened it.

    old_value/new_value are stored as strings rather than typed columns
    so one table can record changes to fields of any type (int hours,
    bool flags) without a column per setting. NULL old_value means the
    field had no DB override before the change - distinct from the
    string "None".

    Not user-scoped in the usual sense: actor_user_id is who *made* the
    change, not who owns the row, so the repository pattern's per-user
    read filtering does not apply (reads are admin-only).
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, index=True
    )

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, actor_user_id={self.actor_user_id}, "
            f"action={self.action}, field_name={self.field_name})>"
        )


class SystemSettings(Base):
    """Singleton row holding runtime-mutable LLM/embedding provider and
    data-retention config.

    Exactly one row is expected to exist (id="default"). Unlike other models
    here, this is deliberately NOT user-scoped — it's a system-wide setting,
    not per-tenant data — so it has no user_id and the repository pattern's
    usual per-user filtering does not apply.

    Every column is nullable because NULL means "no override, use the env
    default" (see app.services.system_settings_service._resolve_field). For
    the retention columns this matters twice over: 0 is a legitimate
    override meaning "purge immediately", so "unset" cannot be encoded as a
    falsy value.
    """

    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conversation_retention_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cleanup_on_logout: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    knowledge_base_purge_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_key_purge_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self):
        return f"<SystemSettings(id={self.id}, llm_provider={self.llm_provider}, embedding_provider={self.embedding_provider})>"
