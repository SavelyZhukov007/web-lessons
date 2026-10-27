"""Разовые занятия на конкретную дату.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("one_off_date", sa.String(length=10), nullable=True))
    op.create_index("ix_sessions_one_off_date", "sessions", ["one_off_date"])


def downgrade() -> None:
    op.drop_index("ix_sessions_one_off_date", table_name="sessions")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("one_off_date")
