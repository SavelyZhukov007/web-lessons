"""Separate Web Push preferences for cancellations and moves."""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("push_subscriptions", sa.Column("announcements_only", sa.Boolean, nullable=False, server_default=sa.false()))
    for name in ("cancellations", "moves"):
        op.add_column("push_subscriptions", sa.Column(name, sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade():
    op.execute(sa.text("DELETE FROM push_subscriptions WHERE announcements_only"))
    with op.batch_alter_table("push_subscriptions") as batch:
        for name in ("announcements_only", "cancellations", "moves"):
            batch.drop_column(name)
