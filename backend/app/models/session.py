from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ClubSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 6", name="ck_sessions_weekday_range"),
        CheckConstraint("start_time < end_time", name="ck_sessions_valid_interval"),
        CheckConstraint(
            "start_time GLOB '[0-2][0-9]:[0-5][0-9]' AND end_time GLOB '[0-2][0-9]:[0-5][0-9]'",
            name="ck_sessions_time_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"), index=True
    )
    weekday: Mapped[int] = mapped_column()
    # NULL — каждую неделю; дата — единственное занятие на этот день.
    one_off_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    club: Mapped[Club] = relationship(back_populates="sessions")
    room: Mapped[Room] = relationship(back_populates="sessions")
    exceptions: Mapped[list[SessionException]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
