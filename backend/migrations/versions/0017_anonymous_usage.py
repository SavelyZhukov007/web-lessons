"""Anonymous daily usage (frozen DDL, independent of future model edits)."""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("usage_batches", sa.Column("id", sa.String(32), primary_key=True), sa.Column("day", sa.Date(), nullable=False))
    op.create_index("ix_usage_batches_day", "usage_batches", ["day"])
    op.create_table(
        "usage_counters",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("metric", sa.String(32), primary_key=True),
        sa.Column("bucket", sa.String(16), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "client_error_counts",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("build", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("line", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("client_error_counts")
    op.drop_table("usage_counters")
    op.drop_index("ix_usage_batches_day", table_name="usage_batches")
    op.drop_table("usage_batches")
