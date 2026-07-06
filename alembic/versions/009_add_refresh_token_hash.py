"""add refresh_token_hash column to device_tokens

Revision ID: 009_add_refresh_token_hash
Revises: 008_add_fk_indexes
Create Date: 2026-07-03

Audit C4: /auth/token/refresh selected ALL unrevoked, unexpired device tokens
across every user and AES-decrypted each in a Python loop to find a match —
O(all devices) per refresh call. This adds a SHA-256 hash of the raw refresh
token alongside the existing encrypted column so the endpoint can do an
indexed equality lookup instead.

Backfill strategy: the hash cannot be derived from the existing ciphertext
without the vault key at migration time, so the column is nullable. Existing
rows get their hash populated lazily — daily.auth.router.token_refresh falls
back to the old full scan ONLY for rows where refresh_token_hash IS NULL, and
backfills the hash on a successful match. The column is fully backfilled
(and the fallback path effectively dead) once every existing device has
refreshed at least once.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_refresh_token_hash"
down_revision: Union[str, Sequence[str], None] = "008_add_fk_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable refresh_token_hash column + index to device_tokens."""
    op.add_column(
        "device_tokens",
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_device_tokens_refresh_token_hash",
        "device_tokens",
        ["refresh_token_hash"],
        unique=False,
    )


def downgrade() -> None:
    """Drop refresh_token_hash column + index from device_tokens."""
    op.drop_index("ix_device_tokens_refresh_token_hash", table_name="device_tokens")
    op.drop_column("device_tokens", "refresh_token_hash")
