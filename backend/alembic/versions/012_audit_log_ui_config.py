"""Add audit_log_ui_enabled column on system_settings

Adds issue #45's audit-log-viewer visibility switch onto the same
DB-override pattern as tracing/rate-limit config added in 010/011: NULL
means "no override, use the AUDIT_LOG_UI_ENABLED env default" (default
True - transparent by default), see
app.services.audit_log_ui_config_service.resolve_audit_log_ui_config.

Unlike tracing_enabled, this column is resolved per-call, not once at
startup - hiding/showing a nav button and view has no "requires restart"
constraint, so it follows guardrail/rate-limit config's resolution timing
rather than tracing's.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, 009, and 010 were hand-written: the local
dev Postgres instance is shared with Keycloak, so autogenerate's diff also
picks up Keycloak's entire schema as "to be dropped".

Revision ID: 012
Revises: 011
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("audit_log_ui_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "audit_log_ui_enabled")
