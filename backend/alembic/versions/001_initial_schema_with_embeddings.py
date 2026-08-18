"""Initial schema with embeddings

Revision ID: 001
Revises:
Create Date: 2026-08-18 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('secret_value', sa.String(512), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create knowledge_base table
    op.create_table(
        'knowledge_base',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('doc_metadata', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create embeddings table with pgvector
    # Create with a placeholder column first, then alter
    op.create_table(
        'embeddings',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('doc_id', sa.String(36), nullable=False, index=True),
        sa.Column('embed_metadata', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['doc_id'], ['knowledge_base.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Add embedding column with vector type using raw SQL
    # Create a vector of zeros with 1536 dimensions as default
    op.execute("ALTER TABLE embeddings ADD COLUMN embedding vector(1536) NOT NULL DEFAULT (array_fill(0, ARRAY[1536]))::vector")


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table('embeddings')
    op.drop_table('knowledge_base')
    op.drop_table('api_keys')
    # Don't drop the vector extension as it may be needed by other services
