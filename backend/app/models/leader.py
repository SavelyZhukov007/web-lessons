from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .club import Club


class Leader(Base):
    __tablename__ = "leaders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    position: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(Text, default="")
    # доступ преподавателя в приложение: хранится только SHA-256 токена T-…; None — доступа нет / отозван
    access_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)  # уникальный индекс (миграция 0005 без пересоздания leaders)
    access_issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    clubs: Mapped[list[Club]] = relationship(back_populates="leader")
