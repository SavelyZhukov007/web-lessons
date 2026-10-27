from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("name", "building", name="uq_rooms_name_building"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    building: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    capacity: Mapped[int | None] = mapped_column(nullable=True, default=None)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    remote_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    remote_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    sessions: Mapped[list[ClubSession]] = relationship(back_populates="room")
    moved_exceptions: Mapped[list[SessionException]] = relationship(
        back_populates="new_room"
    )
