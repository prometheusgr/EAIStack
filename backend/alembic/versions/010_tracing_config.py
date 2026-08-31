"""Add tracing_enabled column on system_settings

Moves issue #4's LLM observability on/off switch onto the same DB-override
pattern as the guardrail and retention config added in 008/009: NULL means
"no override, use the TRACING_ENABLED env default" (see
app.services.tracing_config_service.resolve_tracing_config).

Unlike every other overridable column on this table, tracing_enabled is
resolved once at process startup (app.main's lifespan hook), not per-call -
there is no supported way to re-instrument a running process's OTel tracer
provider - so a change via the settings screen requires a backend restart
to take effect. That is a runtime-resolution detail, not a schema one: the
column itself follows the exact same nullable-override shape as its
siblings.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, and 009 were hand-written: the local dev
Postgres instance is shared with Keycloak, so autogenerate's diff also
picks up Keycloak's entire schema as "to be dropped".

Revision ID: 010
Revises: 009
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("tracing_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "tracing_enabled")
