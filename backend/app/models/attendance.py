from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Attendance(Base):
    """Отметка посещения: занятие (session_id + original_date) + анонимный ID студента. Имён студентов на сервере нет.
    Хранится 21 день (services/attendance_retention)."""

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("session_id", "occurrence_date", "student_id", name="uq_attendance_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    occurrence_date: Mapped[str] = mapped_column(String(10), index=True)
    student_id: Mapped[str] = mapped_column(String(40), index=True)
    method: Mapped[str] = mapped_column(String(10), default="qr")  # qr | manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class QrNonce(Base):
    """Одноразовые nonce отметок (защита от повторной отправки). Чистятся по expires_at."""

    __tablename__ = "qr_nonces"

    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class StudentDevice(Base):
    """Доказательство устройства для «Мои посещения»: SHA-256 токена устройства, зарегистрированного при первой отметке ID.
    Токен = HMAC(секрет устройства, "device-token") — восстанавливается вместе с резервным кодом."""

    __tablename__ = "student_devices"

    student_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
