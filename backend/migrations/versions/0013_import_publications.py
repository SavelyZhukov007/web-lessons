"""Store atomic publication history and track later schedule edits."""
import sqlalchemy as sa
from alembic import op

from backend.app.models.import_publication import revision_triggers

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _original_triggers():
    # Freeze this migration's schema: future journal tables belong in their own migrations.
    original = ("categories", "leaders", "rooms", "clubs", "sessions", "club_leaders", "session_leaders", "session_rooms", "session_exceptions")
    return [(name, sql) for name, sql in revision_triggers() if any(name.startswith(f"schedule_revision_{table}_") for table in original)]


def upgrade():
    op.create_table(
        "import_publications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("draft_id", sa.Integer, unique=True),
        sa.Column("metadata_json", sa.Text, nullable=False),
        sa.Column("changes_json", sa.Text, nullable=False),
        sa.Column("rolled_back", sa.Boolean, nullable=False),
    )
    op.create_table(
        "schedule_row_revisions",
        sa.Column("table_name", sa.String, primary_key=True),
        sa.Column("row_key", sa.String, primary_key=True),
        sa.Column("revision", sa.String, nullable=False),
    )
    for _, statement in _original_triggers():
        op.execute(statement)


def downgrade():
    for name, _ in _original_triggers():
        op.execute(f"DROP TRIGGER {name}")
    op.drop_table("schedule_row_revisions")
    op.drop_table("import_publications")
