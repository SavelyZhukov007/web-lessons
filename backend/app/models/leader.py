"""Илья и Артём. TODO: SQLAlchemy-модель.
leaders: id, name, position, contact.
Использовать Base из ../database.py. Пока таблица не реализована.
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from .club import Club


class Leader(Base):
    __tablename__ = "leaders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    position: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(Text, default="")
    clubs: Mapped[list["Club"]] = relationship(back_populates="leader")
