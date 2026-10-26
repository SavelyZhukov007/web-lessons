"""Обезличенная установка сайта / PWA для счётчика пользователей: SHA-256 случайного id из localStorage, вид и даты.
Без IP и User-Agent; запись забывается через 60 дней без активности. Установки APK считаются по app_devices."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Install(Base):
    __tablename__ = "installs"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="web")  # web | ios-pwa | pwa (Android/desktop standalone)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
