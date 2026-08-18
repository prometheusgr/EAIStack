"""Repository module for data access abstraction."""

from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.api_key_repository import APIKeyRepository

__all__ = [
    "EmbeddingRepository",
    "APIKeyRepository",
]
