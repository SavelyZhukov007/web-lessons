"""Илья и Артём. TODO: SQLAlchemy-модель.
session_exceptions: id, session_id, original_date, type, new_date, new_start_time, new_end_time, new_room_id, comment. Одна запись на session_id + original_date.
Использовать Base из ../database.py. Пока таблица не реализована.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class SessionException(Base):
    __tablename__ = "session_exceptions"
    __table_args__ = (
        UniqueConstraint("session_id", "original_date", name="uq_session_exceptions_occurrence"),
        CheckConstraint("type IN ('cancelled', 'moved')", name="ck_session_exceptions_type"),
        CheckConstraint(
            "("
            "type = 'cancelled' AND new_date IS NULL AND new_start_time IS NULL AND new_end_time IS NULL AND new_room_id IS NULL"
            ") OR ("
            "type = 'moved' AND new_date IS NOT NULL AND new_start_time IS NOT NULL AND new_end_time IS NOT NULL "
            "AND new_room_id IS NOT NULL AND new_start_time < new_end_time"
            ")",
            name="ck_session_exceptions_shape",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    original_date: Mapped[str] = mapped_column(String(10), index=True)
    type: Mapped[str] = mapped_column(String(10))
    new_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    new_end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    new_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    comment: Mapped[str] = mapped_column(Text, default="")
    session: Mapped["ClubSession"] = relationship(back_populates="exceptions")
    new_room: Mapped["Room | None"] = relationship(back_populates="moved_exceptions")
