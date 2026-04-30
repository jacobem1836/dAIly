"""pairing_codes_add_email_nullable_user

Revision ID: 006
Revises: 005
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pairing_codes", sa.Column("email", sa.String(length=255), nullable=True))
    op.alter_column("pairing_codes", "user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("pairing_codes", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("pairing_codes", "email")
