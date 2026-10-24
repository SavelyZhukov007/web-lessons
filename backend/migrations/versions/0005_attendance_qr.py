"""Анонимная посещаемость: attendance.student_id вместо имени/устройства, qr_nonces, доступ преподавателей (leaders.access_hash)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # старые отметки содержали имена — удаляем (политика: на сервере только анонимные ID, хранение 21 день)
    op.execute("DELETE FROM attendance")
    with op.batch_alter_table("attendance", recreate="always") as batch:
        batch.drop_constraint("uq_attendance_device", type_="unique")
        batch.drop_column("student_name")
        batch.alter_column("device_id", new_column_name="student_id", existing_type=sa.String(length=64), type_=sa.String(length=40))
        batch.add_column(sa.Column("method", sa.String(length=10), nullable=False, server_default="qr"))
    with op.batch_alter_table("attendance") as batch:
        batch.create_unique_constraint("uq_attendance_student", ["session_id", "occurrence_date", "student_id"])
        batch.create_index(batch.f("ix_attendance_student_id"), ["student_id"], unique=False)
    op.create_table(
        "qr_nonces",
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("nonce"),
    )
    op.create_table(
        "student_devices",
        sa.Column("student_id", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("student_id"),
    )
    # без пересоздания таблицы leaders: на заполненной БД на неё ссылаются sessions (FOREIGN KEY), DROP TABLE упадёт
    op.add_column("leaders", sa.Column("access_hash", sa.String(length=64), nullable=True))
    op.add_column("leaders", sa.Column("access_issued_at", sa.DateTime(), nullable=True))
    op.create_index("ix_leaders_access_hash", "leaders", ["access_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_leaders_access_hash", table_name="leaders")
    with op.batch_alter_table("leaders") as batch:
        batch.drop_column("access_issued_at")
        batch.drop_column("access_hash")
    op.drop_table("student_devices")
    op.drop_table("qr_nonces")
    op.execute("DELETE FROM attendance")
    with op.batch_alter_table("attendance", recreate="always") as batch:
        batch.drop_index(batch.f("ix_attendance_student_id"))
        batch.drop_constraint("uq_attendance_student", type_="unique")
    with op.batch_alter_table("attendance", recreate="always") as batch:
        batch.drop_column("method")
        batch.alter_column("student_id", new_column_name="device_id", existing_type=sa.String(length=40), type_=sa.String(length=64))
        batch.add_column(sa.Column("student_name", sa.String(length=100), nullable=False, server_default=""))
        batch.create_unique_constraint("uq_attendance_device", ["session_id", "occurrence_date", "device_id"])
