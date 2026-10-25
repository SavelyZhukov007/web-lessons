from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Broadcast(Base):
    """Объявление (рассылка) администратора. audience: all — всем; clubs — подписчикам club_ids (JSON-список).
    session_ids (JSON) — уточнение «какие занятия» для текста/журнала; получатели всё равно подписчики кружков."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    audience: Mapped[str] = mapped_column(String(10), default="all")
    club_ids: Mapped[str] = mapped_column(Text, default="[]")
    session_ids: Mapped[str] = mapped_column(Text, default="[]")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True)
    author_login: Mapped[str] = mapped_column(String(64), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    web_sent: Mapped[int] = mapped_column(Integer, default=0)
    web_failed: Mapped[int] = mapped_column(Integer, default=0)
    apk_targets: Mapped[int] = mapped_column(Integer, default=0)
    fcm_sent: Mapped[int] = mapped_column(Integer, default=0)
    fcm_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class AppDevice(Base):
    """Установка APK: опрашивает /api/announcements (резервный путь) и, если собрана с Firebase, регистрирует FCM-токен.
    Хранится SHA-256 случайного id установки, «мои кружки», переключатели и FCM-токен; запись забывается через 60 дней."""

    __tablename__ = "app_devices"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_ids: Mapped[str] = mapped_column(Text, default="[]")
    announcements: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_changes: Mapped[bool] = mapped_column(Boolean, default=True)
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    platform: Mapped[str] = mapped_column(String(16), default="android")
    app_version: Mapped[str] = mapped_column(String(32), default="")
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
