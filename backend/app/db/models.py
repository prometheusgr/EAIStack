"""SQLAlchemy models for database schema."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

Base = declarative_base()


class ProviderEnum(str, enum.Enum):
    """Supported API key providers."""
    openai = "openai"
    anthropic = "anthropic"
    huggingface = "huggingface"
    custom = "custom"


class APIKey(Base):
    """API Key model for storing user credentials."""
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    provider = Column(SQLEnum(ProviderEnum), nullable=False)
    secret_value = Column(String(512), nullable=False)  # In production, encrypt this
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True, default=None)

    def __repr__(self):
        return f"<APIKey(id={self.id}, name={self.name}, provider={self.provider}, user_id={self.user_id})>"


# TODO: Add models for:
# - Sessions (conversation threads, keyed by user_id + thread_id)
# - Documents (metadata, stored in MinIO)
# - Embeddings (stored in pgvector)
# - Guardrail audit logs
