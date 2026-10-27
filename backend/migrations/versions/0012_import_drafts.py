"""Черновики импорта отдельно от действующего расписания."""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("import_drafts", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("filename", sa.String(200), nullable=False),
                    sa.Column("rows_json", sa.Text, nullable=False),
                    sa.Column("decisions_json", sa.Text, nullable=False),
                    sa.Column("status", sa.String(20), nullable=False))


def downgrade():
    op.drop_table("import_drafts")
