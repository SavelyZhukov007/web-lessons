"""Дополнительные руководители и аудитории; неизвестная вместимость."""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    # Rebuilding a referenced SQLite table with FKs enabled would fail or affect
    # dependent records. Restore FK checks and verify the database afterwards.
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=OFF")
        try:
            with op.batch_alter_table("rooms", recreate="always") as batch:
                batch.alter_column("building", existing_type=sa.Text(), nullable=True)
                batch.alter_column("capacity", existing_type=sa.Integer(), nullable=True)
                batch.add_column(sa.Column("is_remote", sa.Boolean(), nullable=False, server_default=sa.false()))
                batch.add_column(sa.Column("remote_url", sa.Text(), nullable=False, server_default=""))
                batch.add_column(sa.Column("remote_instructions", sa.Text(), nullable=False, server_default=""))
        finally:
            op.execute("PRAGMA foreign_keys=ON")
    for table, first, foreign in (("club_leaders", "club_id", "clubs.id"), ("session_leaders", "session_id", "sessions.id"), ("session_rooms", "session_id", "sessions.id")):
        second = "room_id" if table == "session_rooms" else "leader_id"
        target = "rooms.id" if second == "room_id" else "leaders.id"
        op.create_table(table, sa.Column(first, sa.Integer, sa.ForeignKey(foreign, ondelete="CASCADE"), primary_key=True),
                        sa.Column(second, sa.Integer, sa.ForeignKey(target, ondelete="RESTRICT"), primary_key=True))
    op.execute("INSERT INTO club_leaders (club_id, leader_id) SELECT id, leader_id FROM clubs")
    op.execute("INSERT INTO session_rooms (session_id, room_id) SELECT id, room_id FROM sessions")


def downgrade():
    conn = op.get_bind()
    checks = ["SELECT count(*) FROM session_leaders", "SELECT count(*) FROM club_leaders l JOIN clubs c ON c.id=l.club_id WHERE l.leader_id != c.leader_id",
              "SELECT count(*) FROM session_rooms r JOIN sessions s ON s.id=r.session_id WHERE r.room_id != s.room_id",
              "SELECT count(*) FROM rooms WHERE capacity IS NULL OR building IS NULL OR is_remote != 0 OR remote_url != '' OR remote_instructions != ''"]
    if any(conn.exec_driver_sql(q).scalar() for q in checks):
        raise RuntimeError("Откат потеряет дополнительные связи или сведения; восстановите резервную копию")
    for table in ("session_rooms", "session_leaders", "club_leaders"):
        op.drop_table(table)
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=OFF")
        try:
            with op.batch_alter_table("rooms", recreate="always") as batch:
                batch.drop_column("remote_instructions")
                batch.drop_column("remote_url")
                batch.drop_column("is_remote")
                batch.alter_column("building", existing_type=sa.Text(), nullable=False)
                batch.alter_column("capacity", existing_type=sa.Integer(), nullable=False)
        finally:
            op.execute("PRAGMA foreign_keys=ON")
