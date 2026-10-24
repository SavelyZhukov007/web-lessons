"""attendance: отметки посещения по QR-коду (phase 2 C)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("occurrence_date", sa.String(length=10), nullable=False),
        sa.Column("student_name", sa.String(length=100), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "occurrence_date", "device_id", name="uq_attendance_device"),
    )
    with op.batch_alter_table("attendance") as batch:
        batch.create_index(batch.f("ix_attendance_session_id"), ["session_id"], unique=False)
        batch.create_index(batch.f("ix_attendance_occurrence_date"), ["occurrence_date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("attendance") as batch:
        batch.drop_index(batch.f("ix_attendance_occurrence_date"))
        batch.drop_index(batch.f("ix_attendance_session_id"))
    op.drop_table("attendance")
