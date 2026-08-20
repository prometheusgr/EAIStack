"""Repository for API Key data access."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import APIKey


class APIKeyRepository:
    """Repository for querying and managing API keys."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_by_user(self, user_id: str) -> list[APIKey]:
        """Fetch all active (non-revoked) API keys for a user."""
        return (
            self.db.query(APIKey)
            .filter(
                APIKey.user_id == user_id,
                APIKey.revoked_at.is_(None),
            )
            .all()
        )

    def get_by_id(self, api_key_id: str, user_id: str) -> APIKey | None:
        """Fetch a single API key by ID, verifying user ownership.

        Returns None if key not found or user doesn't own it.
        """
        return (
            self.db.query(APIKey)
            .filter(
                APIKey.id == api_key_id,
                APIKey.user_id == user_id,
            )
            .first()
        )

    def create(self, user_id: str, name: str, provider: str, secret_value: str) -> APIKey:
        """Create a new API key for the user.

        Flushes so the returned APIKey has its generated ID and defaults
        populated. Does not commit; the caller owns the transaction.
        """
        key = APIKey(
            id=str(uuid4()),
            user_id=user_id,
            name=name,
            provider=provider,
            secret_value=secret_value,
        )
        self.db.add(key)
        self.db.flush()
        return key

    def update(self, api_key_id: str, name: str, provider: str) -> None:
        """Update an API key's name and provider.

        Only non-revoked keys can be updated. Does not commit; the caller
        owns the transaction.
        """
        key = self.db.query(APIKey).filter(APIKey.id == api_key_id).first()

        if key and key.revoked_at is None:
            key.name = name
            key.provider = provider
            key.updated_at = datetime.now(timezone.utc)
            self.db.flush()

    def revoke(self, api_key_id: str) -> None:
        """Soft-delete (revoke) an API key by setting revoked_at timestamp.

        Does not commit; the caller owns the transaction.
        """
        key = self.db.query(APIKey).filter(APIKey.id == api_key_id).first()

        if key:
            key.revoked_at = datetime.now(timezone.utc)
            self.db.flush()
