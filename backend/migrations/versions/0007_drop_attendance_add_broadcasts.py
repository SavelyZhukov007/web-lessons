"""Посещаемость удалена; рассылки администратора (объявления).

Удаляются таблицы attendance, qr_nonces, student_devices (QR-отметки, одноразовые nonce, привязка устройств).
Добавляются broadcasts (журнал объявлений), app_devices (обезличенные установки APK для оценки охвата)
и push_subscriptions.announcements (можно отключить объявления, оставив переносы/отмены).

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("student_devices")
    op.drop_table("qr_nonces")
    with op.batch_alter_table("attendance") as batch:
        batch.drop_index(batch.f("ix_attendance_student_id"))
        batch.drop_index(batch.f("ix_attendance_occurrence_date"))
        batch.drop_index(batch.f("ix_attendance_session_id"))
    op.drop_table("attendance")

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=True),
        sa.Column("audience", sa.String(length=10), nullable=False),
        sa.Column("club_ids", sa.Text(), nullable=False),
        sa.Column("session_ids", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("author_login", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("web_sent", sa.Integer(), nullable=False),
        sa.Column("web_failed", sa.Integer(), nullable=False),
        sa.Column("apk_targets", sa.Integer(), nullable=False),
        sa.Column("fcm_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fcm_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    with op.batch_alter_table("broadcasts") as batch:
        batch.create_index(batch.f("ix_broadcasts_author_id"), ["author_id"], unique=False)
        batch.create_index(batch.f("ix_broadcasts_created_at"), ["created_at"], unique=False)
    op.create_table(
        "app_devices",
        sa.Column("id_hash", sa.String(length=64), nullable=False),
        sa.Column("club_ids", sa.Text(), nullable=False),
        sa.Column("announcements", sa.Boolean(), nullable=False),
        sa.Column("notify_changes", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("fcm_token", sa.String(length=512), nullable=True),
        sa.Column("platform", sa.String(length=16), nullable=False, server_default="android"),
        sa.Column("app_version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id_hash"),
        sa.UniqueConstraint("fcm_token"),
    )
    with op.batch_alter_table("app_devices") as batch:
        batch.create_index(batch.f("ix_app_devices_last_seen"), ["last_seen"], unique=False)
    # ADD COLUMN без пересоздания таблицы
    op.add_column("push_subscriptions", sa.Column("announcements", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("push_subscriptions", "announcements")
    with op.batch_alter_table("app_devices") as batch:
        batch.drop_index(batch.f("ix_app_devices_last_seen"))
    op.drop_table("app_devices")
    with op.batch_alter_table("broadcasts") as batch:
        batch.drop_index(batch.f("ix_broadcasts_created_at"))
        batch.drop_index(batch.f("ix_broadcasts_author_id"))
    op.drop_table("broadcasts")

    # структура как после 0005 (данные отметок не восстанавливаются)
    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("occurrence_date", sa.String(length=10), nullable=False),
        sa.Column("student_id", sa.String(length=40), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="qr"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "occurrence_date", "student_id", name="uq_attendance_student"),
    )
    with op.batch_alter_table("attendance") as batch:
        batch.create_index(batch.f("ix_attendance_session_id"), ["session_id"], unique=False)
        batch.create_index(batch.f("ix_attendance_occurrence_date"), ["occurrence_date"], unique=False)
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
