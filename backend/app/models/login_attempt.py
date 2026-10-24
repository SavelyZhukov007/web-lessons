from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class LoginAttempt(Base):
    """Неудачная попытка входа (SEC-03): окно по времени, ключ (ip, login), переживает рестарт."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_ip_login_time", "ip", "login", "attempted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64))
    login: Mapped[str] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
