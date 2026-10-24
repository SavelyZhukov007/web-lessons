"""refresh-токены с ротацией: admin_sessions.refresh_hash / refresh_prev_hash / refresh_rotated_at

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admin_sessions") as batch:
        batch.add_column(sa.Column("refresh_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("refresh_prev_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("refresh_rotated_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_admin_sessions_refresh_hash", ["refresh_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("admin_sessions") as batch:
        batch.drop_index("ix_admin_sessions_refresh_hash")
        batch.drop_column("refresh_rotated_at")
        batch.drop_column("refresh_prev_hash")
        batch.drop_column("refresh_hash")
