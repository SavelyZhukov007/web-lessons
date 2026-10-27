"""Учебные периоды и повторяемость, старые занятия сохраняются."""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("academic_periods", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("name", sa.String(160), nullable=False),
                    sa.Column("start_date", sa.String(10), nullable=False),
                    sa.Column("end_date", sa.String(10), nullable=False),
                    sa.Column("even_week_start", sa.String(10), nullable=False))
    op.create_table("no_class_days", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("period_id", sa.Integer, sa.ForeignKey("academic_periods.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("date", sa.String(10), nullable=False), sa.Column("reason", sa.String(255), nullable=False),
                    sa.UniqueConstraint("period_id", "date", name="uq_no_class_period_date"))
    op.create_index("ix_no_class_days_period_id", "no_class_days", ["period_id"])
    # SQLite ALTER avoids recreating sessions and cascading deletion of its exceptions.
    op.execute("ALTER TABLE sessions ADD COLUMN period_id INTEGER REFERENCES academic_periods(id)")
    op.add_column("sessions", sa.Column("repeat", sa.String(12), nullable=False, server_default="weekly"))
    op.create_index("ix_sessions_period_id", "sessions", ["period_id"])
    op.execute("UPDATE sessions SET repeat = 'once' WHERE one_off_date IS NOT NULL")


def downgrade():
    op.drop_index("ix_sessions_period_id", table_name="sessions")
    op.drop_column("sessions", "repeat")
    op.drop_column("sessions", "period_id")
    op.drop_index("ix_no_class_days_period_id", table_name="no_class_days")
    op.drop_table("no_class_days")
    op.drop_table("academic_periods")
