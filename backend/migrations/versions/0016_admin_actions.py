"""Extend safe undo row revisions to academic periods and holidays.

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    from backend.app.models.broadcast_schedule import BroadcastSchedule, BroadcastReceipt
    BroadcastSchedule.__table__.create(op.get_bind(), checkfirst=True)
    BroadcastReceipt.__table__.create(op.get_bind(), checkfirst=True)
    from backend.app.models.import_publication import revision_triggers
    for name, statement in revision_triggers():
        if any(f"_{table}_" in name for table in ("academic_periods", "no_class_days")):
            op.execute(statement)


def downgrade():
    op.drop_table("broadcast_receipts")
    op.drop_table("broadcast_schedules")
    for table in ("academic_periods", "no_class_days"):
        for action in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS schedule_revision_{table}_{action}")
