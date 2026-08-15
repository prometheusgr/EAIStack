"""SQLAlchemy models for database schema."""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# TODO: Add models for:
# - Sessions (conversation threads, keyed by user_id + thread_id)
# - Documents (metadata, stored in MinIO)
# - Embeddings (stored in pgvector)
# - Guardrail audit logs
