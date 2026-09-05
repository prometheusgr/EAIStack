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
        conversation_retention_hours: int | None = None,
        cleanup_on_logout: bool | None = None,
        knowledge_base_purge_days: int | None = None,
        api_key_purge_days: int | None = None,
        max_input_length: int | None = None,
        guardrails_input_enabled: bool | None = None,
        guardrails_output_enabled: bool | None = None,
        tracing_enabled: bool | None = None,
        rate_limit_enabled: bool | None = None,
        rate_limit_chat_capacity: int | None = None,
        rate_limit_chat_refill_per_minute: int | None = None,
        rate_limit_auth_capacity: int | None = None,
        rate_limit_auth_refill_per_minute: int | None = None,
        audit_log_ui_enabled: bool | None = None,
        retention_notice_enabled: bool | None = None,
    ) -> SystemSettings:
        """Create or update the singleton settings row.

        Every field is written on every call: None means "no override, fall
        back to the env default", so omitting one clears it rather than
        leaving the previous value in place. The retention and guardrail
        fields default to None so a caller changing only provider config
        need not name them.

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
        settings_row.conversation_retention_hours = conversation_retention_hours
        settings_row.cleanup_on_logout = cleanup_on_logout
        settings_row.knowledge_base_purge_days = knowledge_base_purge_days
        settings_row.api_key_purge_days = api_key_purge_days
        settings_row.max_input_length = max_input_length
        settings_row.guardrails_input_enabled = guardrails_input_enabled
        settings_row.guardrails_output_enabled = guardrails_output_enabled
        settings_row.tracing_enabled = tracing_enabled
        settings_row.rate_limit_enabled = rate_limit_enabled
        settings_row.rate_limit_chat_capacity = rate_limit_chat_capacity
        settings_row.rate_limit_chat_refill_per_minute = rate_limit_chat_refill_per_minute
        settings_row.rate_limit_auth_capacity = rate_limit_auth_capacity
        settings_row.rate_limit_auth_refill_per_minute = rate_limit_auth_refill_per_minute
        settings_row.audit_log_ui_enabled = audit_log_ui_enabled
        settings_row.retention_notice_enabled = retention_notice_enabled
        settings_row.updated_by = updated_by

        self.db.flush()
        return settings_row
