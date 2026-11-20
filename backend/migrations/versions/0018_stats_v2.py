"""Статистика v2: usage_daily (платформа, канал, версия, dim), usage_monthly, perf_daily, install_activity,
retention_weekly, version_daily; app_devices.first_seen. Данные usage_counters переносятся в usage_daily (frozen DDL).

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("channel", sa.String(1), primary_key=True),
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("metric", sa.String(32), primary_key=True),
        sa.Column("dim", sa.String(32), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO usage_daily (day, platform, channel, version, metric, dim, count) "
        "SELECT day, platform, 'p', '', metric, bucket, count FROM usage_counters"
    )
    op.drop_table("usage_counters")
    op.create_table(
        "usage_monthly",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("channel", sa.String(1), primary_key=True),
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("metric", sa.String(40), primary_key=True),
        sa.Column("dim", sa.String(32), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "perf_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("metric", sa.String(16), primary_key=True),
        sa.Column("bucket", sa.String(8), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "install_activity",
        sa.Column("id_hmac", sa.String(64), primary_key=True),
        sa.Column("platform", sa.String(12), nullable=False),
        sa.Column("channel", sa.String(1), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("last_day", sa.Date(), nullable=False),
        sa.Column("days_bits", sa.String(32), nullable=False),
    )
    op.create_index("ix_install_activity_first_day", "install_activity", ["first_day"])
    op.create_index("ix_install_activity_last_day", "install_activity", ["last_day"])
    op.create_table(
        "retention_weekly",
        sa.Column("cohort_week", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("week_n", sa.Integer(), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
    )
    op.create_table(
        "version_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("active", sa.Integer(), nullable=False),
    )
    op.add_column("app_devices", sa.Column("first_seen", sa.DateTime(), nullable=True))
    op.execute("UPDATE app_devices SET first_seen = last_seen WHERE first_seen IS NULL")


def downgrade():
    with op.batch_alter_table("app_devices") as batch:
        batch.drop_column("first_seen")
    op.drop_table("version_daily")
    op.drop_table("retention_weekly")
    op.drop_index("ix_install_activity_last_day", table_name="install_activity")
    op.drop_index("ix_install_activity_first_day", table_name="install_activity")
    op.drop_table("install_activity")
    op.drop_table("perf_daily")
    op.drop_table("usage_monthly")
    op.create_table(
        "usage_counters",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(12), primary_key=True),
        sa.Column("metric", sa.String(32), primary_key=True),
        sa.Column("bucket", sa.String(16), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO usage_counters (day, platform, metric, bucket, count) "
        "SELECT day, platform, metric, substr(dim, 1, 16), sum(count) FROM usage_daily GROUP BY day, platform, metric, substr(dim, 1, 16)"
    )
    op.drop_table("usage_daily")
