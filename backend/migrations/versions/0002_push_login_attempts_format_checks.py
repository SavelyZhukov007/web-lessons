"""push_subscriptions, login_attempts, CHECK на формат времени/даты

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TIME = "'[0-2][0-9]:[0-5][0-9]'"
DATE = "'[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "push_subscriptions" not in tables:
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("p256dh", sa.String(length=255), nullable=False),
            sa.Column("auth", sa.String(length=255), nullable=False),
            sa.Column("club_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("push_subscriptions") as batch:
            batch.create_index(batch.f("ix_push_subscriptions_club_id"), ["club_id"], unique=False)
            batch.create_index("ix_push_subscriptions_endpoint_club", ["endpoint", "club_id"], unique=False)

    if "login_attempts" not in tables:
        op.create_table(
            "login_attempts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=False),
            sa.Column("login", sa.String(length=64), nullable=False),
            sa.Column("attempted_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("login_attempts") as batch:
            batch.create_index("ix_login_attempts_ip_login_time", ["ip", "login", "attempted_at"], unique=False)

    # DB-03: формат HH:MM / YYYY-MM-DD на уровне БД. Если в старой БД есть мусор — миграция упадёт ЯВНО (лучше, чем молча).
    with op.batch_alter_table("sessions") as batch:
        batch.create_check_constraint(
            "ck_sessions_time_format", f"start_time GLOB {TIME} AND end_time GLOB {TIME}"
        )
    with op.batch_alter_table("session_exceptions") as batch:
        batch.create_check_constraint(
            "ck_session_exceptions_format",
            f"original_date GLOB {DATE} AND (new_date IS NULL OR new_date GLOB {DATE}) "
            f"AND (new_start_time IS NULL OR new_start_time GLOB {TIME}) "
            f"AND (new_end_time IS NULL OR new_end_time GLOB {TIME})",
        )


def downgrade() -> None:
    with op.batch_alter_table("session_exceptions") as batch:
        batch.drop_constraint("ck_session_exceptions_format", type_="check")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("ck_sessions_time_format", type_="check")
    op.drop_table("login_attempts")
    op.drop_table("push_subscriptions")
