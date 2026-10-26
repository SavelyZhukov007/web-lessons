"""Счётчик пользователей: таблица installs (обезличенные установки сайта / PWA; APK — по app_devices).

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installs",
        sa.Column("id_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id_hash"),
    )
    with op.batch_alter_table("installs") as batch:
        batch.create_index(batch.f("ix_installs_first_seen"), ["first_seen"], unique=False)
        batch.create_index(batch.f("ix_installs_last_seen"), ["last_seen"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("installs") as batch:
        batch.drop_index(batch.f("ix_installs_last_seen"))
        batch.drop_index(batch.f("ix_installs_first_seen"))
    op.drop_table("installs")
