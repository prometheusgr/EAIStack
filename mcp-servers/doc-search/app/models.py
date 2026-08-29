"""Read-only view of the tables doc-search queries.

These mirror backend/app/db/models.py's KnowledgeBase, Embedding, and
SystemSettings column-for-column. Alembic in backend/ remains the sole
schema authority (see CLAUDE.md's Phase 4a note) — doc-search never runs
migrations and never writes to knowledge_base, embeddings, or
system_settings; it only reads. Test fixtures create these tables in an
isolated test database via Base.metadata.create_all, never against a
shared/production database.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for doc-search's read-only model mirror."""


def utc_now() -> datetime:
    """Get current UTC time (timezone-aware, matches backend/app/db/models.py)."""
    return datetime.now(timezone.utc)


class KnowledgeBase(Base):
    """Mirrors backend/app/db/models.py's KnowledgeBase."""

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
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class Embedding(Base):
    """Mirrors backend/app/db/models.py's Embedding.

    One row per chunk, not per document, since backend/app/db/models.py's
    migration 006 (see that migration's docstring): chunk_index/chunk_text/
    heading_path let doc-search return the matching passage directly,
    without re-splitting the document at query time.
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
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class SystemSettings(Base):
    """Mirrors backend/app/db/models.py's SystemSettings (embedding columns only
    — doc-search has no reason to read the LLM or retention columns).
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
