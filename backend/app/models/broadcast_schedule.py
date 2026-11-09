"""Scheduled announcements are drafts, not published feed records (monotonic legacy cursor)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .broadcast import _utcnow


class BroadcastSchedule(Base):
    __tablename__ = "broadcast_schedules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    error: Mapped[str] = mapped_column(String(500), default="")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    author_login: Mapped[str] = mapped_column(String(64))
    broadcast_id: Mapped[int | None] = mapped_column(ForeignKey("broadcasts.id", ondelete="SET NULL"), nullable=True)


class BroadcastReceipt(Base):
    __tablename__ = "broadcast_receipts"
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), primary_key=True)
    install_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[str] = mapped_column(String(12), primary_key=True)
    shown_at: Mapped[datetime] = mapped_column(DateTime)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
