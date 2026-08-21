"""Repository for SystemSettings data access."""

from sqlalchemy.orm import Session

from app.db.models import SystemSettings

_SINGLETON_ID = "default"


class SystemSettingsRepository:
    """Repository for the singleton runtime-settings row.

    Unlike other repositories in this codebase, methods here take no
    user_id: SystemSettings is a system-wide singleton (see its model
    docstring), not per-tenant data, so the usual user-isolation filtering
    does not apply.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get(self) -> SystemSettings | None:
        """Fetch the singleton settings row, or None if it hasn't been created yet."""
        return self.db.query(SystemSettings).filter(SystemSettings.id == _SINGLETON_ID).first()

    def upsert(
        self,
        *,
        llm_provider: str | None,
        llm_url: str | None,
        llm_model: str | None,
        embedding_provider: str | None,
        embedding_url: str | None,
        embedding_model: str | None,
        updated_by: str,
    ) -> SystemSettings:
        """Create or update the singleton settings row.

        Does not commit; the caller owns the transaction.
        """
        settings_row = self.get()

        if settings_row is None:
            settings_row = SystemSettings(id=_SINGLETON_ID)
            self.db.add(settings_row)

        settings_row.llm_provider = llm_provider
        settings_row.llm_url = llm_url
        settings_row.llm_model = llm_model
        settings_row.embedding_provider = embedding_provider
        settings_row.embedding_url = embedding_url
        settings_row.embedding_model = embedding_model
        settings_row.updated_by = updated_by

        self.db.flush()
        return settings_row
