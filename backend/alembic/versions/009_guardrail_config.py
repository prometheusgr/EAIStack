"""Add guardrail config columns on system_settings and the guardrail_patterns table

Adds issue #16's admin-configurable guardrail thresholds/heuristics: an
on/off switch for the input and output guardrails, an overridable
max_input_length, and a table of prompt-injection detection patterns
(built-in, toggleable; or custom, admin-added literal phrases).

The three new system_settings columns are nullable for the same reason
every other overridable column on this table is: NULL means "no override,
use the env default" (see
app.services.guardrail_config_service.resolve_guardrail_config).

guardrail_patterns holds one row per built-in pattern id (seeded lazily and
idempotently by GuardrailPatternRepository.ensure_built_ins_seeded, not by
this migration -- so a future code change adding another built-in pattern
appears here automatically with no further migration) plus any admin-added
custom phrases. pattern_text is NULL for built-in rows: the actual regex
stays in code, reviewed like any other code change, and this table only
ever records on/off state for it. Indexed on source and enabled since
resolving effective guardrail config reads "which built-in rows are
enabled" and "which custom rows are enabled" on every call (see
resolve_guardrail_config).

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003 and 005 were hand-written: the local dev
Postgres instance is shared with Keycloak, so autogenerate's diff also
picks up Keycloak's entire schema as "to be dropped".

Revision ID: 009
Revises: 008
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("max_input_length", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("guardrails_input_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("guardrails_output_enabled", sa.Boolean(), nullable=True),
    )

    op.create_table(
        "guardrail_patterns",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("pattern_text", sa.String(500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guardrail_patterns_source", "guardrail_patterns", ["source"])
    op.create_index("ix_guardrail_patterns_enabled", "guardrail_patterns", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_guardrail_patterns_enabled", table_name="guardrail_patterns")
    op.drop_index("ix_guardrail_patterns_source", table_name="guardrail_patterns")
    op.drop_table("guardrail_patterns")

    op.drop_column("system_settings", "guardrails_output_enabled")
    op.drop_column("system_settings", "guardrails_input_enabled")
    op.drop_column("system_settings", "max_input_length")
