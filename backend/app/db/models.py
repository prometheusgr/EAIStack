"""SQLAlchemy models for database schema."""

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
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
