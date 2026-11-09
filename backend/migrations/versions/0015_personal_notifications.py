"""Opt-in scheduled web notifications and quiet-hours queue."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("push_subscriptions", sa.Column("schedule_settings", sa.Text(), nullable=False, server_default="{}"))
    op.create_table(
        "notification_tasks",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("due", sa.DateTime(), nullable=False),
        sa.Column("expires", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_notification_tasks_target", "notification_tasks", ["target"])
    op.create_index("ix_notification_tasks_due", "notification_tasks", ["due"])


def downgrade():
    op.drop_table("notification_tasks")
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_column("schedule_settings")
