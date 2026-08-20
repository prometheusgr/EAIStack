"""Change embedding vector dimension from 1536 to 768

Switches the embeddings.embedding column from vector(1536) (an OpenAI
ada-002-shaped placeholder, never populated with real data — Phase 3a used
only a deterministic mock) to vector(768), matching nomic-embed-text-v1.5,
the GGUF embedding model adopted for the real llama-cpp embedding provider.
See docs/LLM_SETUP.md for the model rationale.

Revision ID: 002
Revises: 001
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No production data exists at 1536 dims to migrate (Phase 3a is mock-only),
    # so drop and recreate rather than attempting a lossy resize/pad.
    op.execute("ALTER TABLE embeddings DROP COLUMN embedding")
    op.execute(
        "ALTER TABLE embeddings ADD COLUMN embedding vector(768) NOT NULL DEFAULT (array_fill(0, ARRAY[768]))::vector"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE embeddings DROP COLUMN embedding")
    op.execute(
        "ALTER TABLE embeddings ADD COLUMN embedding vector(1536) NOT NULL DEFAULT (array_fill(0, ARRAY[1536]))::vector"
    )
