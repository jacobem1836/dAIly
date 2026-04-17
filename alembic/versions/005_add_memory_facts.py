"""add memory_facts table with pgvector HNSW index

Revision ID: 005
Revises: 004
Create Date: 2026-04-17

Adds:
  - memory_facts: per-user durable facts extracted from voice sessions.
    Uses pgvector VECTOR(1536) for text-embedding-3-small embeddings.
  - Enables pgvector extension (CREATE EXTENSION IF NOT EXISTS vector).
  - HNSW index on embedding column with vector_cosine_ops for ANN retrieval.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector, create memory_facts table, build HNSW index."""
    # Enable pgvector extension (idempotent — safe if already installed)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("source_session_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # HNSW index for cosine-distance ANN search (Phase 9 D-04 dedup + D-06 retrieval).
    # m = 16, ef_construction = 64 are pgvector recommended defaults for
    # small-to-medium tables at M1 scale.
    op.execute(
        "CREATE INDEX memory_facts_embedding_hnsw_idx "
        "ON memory_facts USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Drop memory_facts table. Leave pgvector extension in place."""
    op.drop_table("memory_facts")
