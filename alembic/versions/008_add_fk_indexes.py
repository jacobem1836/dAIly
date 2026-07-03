"""add missing indexes on foreign key columns

Revision ID: 008_add_fk_indexes
Revises: 007_briefing_config_timezone
Create Date: 2026-07-03

Audit H6: Postgres does not auto-index foreign keys. Every `WHERE user_id = X`
query against these tables was sequential-scanning. Adds a btree index on the
user_id FK column for each table that did not already have one covered by an
existing index/unique constraint.

Not included (already covered by an existing index):
  - briefing_config.user_id: covered by its own UniqueConstraint (implicit
    unique index has user_id as the sole/leading column).
  - vip_senders.user_id: covered by uq_vip_user_email UniqueConstraint(user_id,
    email) — user_id is the leftmost column, so Postgres can use this index
    for user_id-only lookups too.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_fk_indexes"
down_revision: Union[str, Sequence[str], None] = "007_briefing_config_timezone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_integration_tokens_user_id", "integration_tokens", "user_id"),
    ("ix_pairing_codes_user_id", "pairing_codes", "user_id"),
    ("ix_device_tokens_user_id", "device_tokens", "user_id"),
    ("ix_signal_log_user_id", "signal_log", "user_id"),
    ("ix_action_log_user_id", "action_log", "user_id"),
]


def upgrade() -> None:
    """Create btree indexes on unindexed FK user_id columns."""
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade() -> None:
    """Drop the FK indexes created by this migration."""
    for index_name, table_name, _column_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
