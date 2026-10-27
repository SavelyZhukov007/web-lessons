from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ClubLeader(Base):
    __tablename__ = "club_leaders"
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id", ondelete="RESTRICT"), primary_key=True)


class SessionLeader(Base):
    __tablename__ = "session_leaders"
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id", ondelete="RESTRICT"), primary_key=True)


class SessionRoom(Base):
    __tablename__ = "session_rooms"
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), primary_key=True)
