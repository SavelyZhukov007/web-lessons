from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class SessionException(Base):
    __tablename__ = "session_exceptions"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "original_date", name="uq_session_exceptions_occurrence"
        ),
        CheckConstraint(
            "original_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]' "
            "AND (new_date IS NULL OR new_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]') "
            "AND (new_start_time IS NULL OR new_start_time GLOB '[0-2][0-9]:[0-5][0-9]') "
            "AND (new_end_time IS NULL OR new_end_time GLOB '[0-2][0-9]:[0-5][0-9]')",
            name="ck_session_exceptions_format",
        ),
        CheckConstraint(
            "type IN ('cancelled', 'moved')", name="ck_session_exceptions_type"
        ),
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
    session: Mapped[ClubSession] = relationship(back_populates="exceptions")
    new_room: Mapped[Room | None] = relationship(back_populates="moved_exceptions")
