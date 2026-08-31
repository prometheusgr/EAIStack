"""Add rate-limit config columns on system_settings

Issue #25: puts chat (per-user) and auth (per-IP) token-bucket rate limits
on the same DB-override pattern as guardrail/retention/tracing config added
in 008/009/010 - NULL means "no override, use the env default" (see
app.services.rate_limit_config_service.resolve_rate_limit_config). Unlike
tracing_enabled, these are resolved per-call (same as guardrail config), so
an admin's change takes effect on the very next request, no restart needed.

rate_limit_enabled is one shared on/off switch for both the chat and auth
limiters, not two independent switches like the guardrails' input/output
split - the two guardrails have materially different trip behavior (reject
vs. sanitize) that justified separate switches; chat and auth rate limiting
share the same trip behavior (429 + Retry-After) and the same underlying
mechanism, so a single kill switch is the right granularity here.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, 009, and 010 were hand-written: the local
dev Postgres instance is shared with Keycloak, so autogenerate's diff also
picks up Keycloak's entire schema as "to be dropped".

Revision ID: 011
Revises: 010
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("rate_limit_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rate_limit_chat_capacity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rate_limit_chat_refill_per_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rate_limit_auth_capacity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rate_limit_auth_refill_per_minute", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "rate_limit_auth_refill_per_minute")
    op.drop_column("system_settings", "rate_limit_auth_capacity")
    op.drop_column("system_settings", "rate_limit_chat_refill_per_minute")
    op.drop_column("system_settings", "rate_limit_chat_capacity")
    op.drop_column("system_settings", "rate_limit_enabled")
