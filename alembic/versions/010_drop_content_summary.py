"""drop content_summary from action_log

Revision ID: 010_drop_content_summary
Revises: 009_add_refresh_token_hash
Create Date: 2026-07-03

Audit M-1: content_summary stored the first 200 chars of the RAW outgoing
message body in plaintext, permanently, contradicting the project's
"no raw bodies stored" architecture constraint. A grep of the codebase found
no reads of this column for any user-facing purpose — it was write-only.
body_hash (SHA-256 of the full body) already covers audit/integrity needs,
so the column is dropped rather than redacted-and-kept.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_drop_content_summary"
down_revision: Union[str, Sequence[str], None] = "009_add_refresh_token_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the content_summary column from action_log."""
    op.drop_column("action_log", "content_summary")


def downgrade() -> None:
    """Re-add content_summary (nullable-safe default for existing rows)."""
    op.add_column(
        "action_log",
        sa.Column(
            "content_summary",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
