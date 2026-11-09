from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PushSubscription(Base):
    """Web Push-подписка браузера. Пустой club_id — все кружки либо общие объявления."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (Index("ix_push_subscriptions_endpoint_club", "endpoint", "club_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True, index=True)
    announcements_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    announcements: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    cancellations: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    moves: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    schedule_settings: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
