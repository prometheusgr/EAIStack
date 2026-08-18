"""Backend service layer for business logic."""

from app.services.embedding_service import generate_embedding

__all__ = ["generate_embedding"]
