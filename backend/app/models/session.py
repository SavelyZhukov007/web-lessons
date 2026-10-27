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
    period_id: Mapped[int | None] = mapped_column(ForeignKey("academic_periods.id"), nullable=True, index=True)
    repeat: Mapped[str] = mapped_column(String(12), default="weekly", server_default="weekly")
    # NULL — каждую неделю; дата — единственное занятие на этот день.
    one_off_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    club: Mapped[Club] = relationship(back_populates="sessions")
    room: Mapped[Room] = relationship(back_populates="sessions")
    rooms: Mapped[list[Room]] = relationship(secondary="session_rooms", lazy="selectin")
    leaders: Mapped[list[Leader]] = relationship(secondary="session_leaders", lazy="selectin")
    exceptions: Mapped[list[SessionException]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    @property
    def room_ids(self):
        return [self.room_id, *sorted({item.id for item in self.rooms} - {self.room_id})]

    @property
    def leader_ids(self):
        return sorted(item.id for item in self.leaders)
