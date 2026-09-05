"""Add retention_notice_enabled column on system_settings

Adds issue #49's end-user-facing retention notice visibility switch onto
the same DB-override pattern as audit_log_ui_enabled added in 012: NULL
means "no override, use the RETENTION_NOTICE_ENABLED env default" (default
True - transparent by default), see
app.services.retention_notice_config_service.resolve_retention_notice_config.

Resolved per-call, not once at startup - same resolution timing as
audit_log_ui_enabled, since hiding/showing a notice has no "requires
restart" constraint.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, 009, 010, and 012 were hand-written: the
local dev Postgres instance is shared with Keycloak, so autogenerate's diff
also picks up Keycloak's entire schema as "to be dropped".

Revision ID: 013
Revises: 012
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("retention_notice_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "retention_notice_enabled")
