"""Роль преподавателя удалена: остаются гость и администратор.

Доступ преподавателей (leaders.access_hash / access_issued_at) отзывается и столбцы удаляются.
Сами руководители (справочник leaders: имя, должность, контакт, связи с кружками) не меняются.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # бывшие преподаватели становятся обычными записями справочника (как гости в приложении): доступ отозван
    op.drop_index("ix_leaders_access_hash", table_name="leaders")
    # без пересоздания leaders (на неё ссылаются sessions/clubs): ALTER TABLE … DROP COLUMN (SQLite >= 3.35)
    op.drop_column("leaders", "access_issued_at")
    op.drop_column("leaders", "access_hash")


def downgrade() -> None:
    op.add_column("leaders", sa.Column("access_hash", sa.String(length=64), nullable=True))
    op.add_column("leaders", sa.Column("access_issued_at", sa.DateTime(), nullable=True))
    op.create_index("ix_leaders_access_hash", "leaders", ["access_hash"], unique=True)
