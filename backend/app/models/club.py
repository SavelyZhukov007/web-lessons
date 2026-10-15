"""Илья и Артём. TODO: SQLAlchemy-модель.
clubs: id, name, description, category_id, leader_id, is_active.
Использовать Base из ../database.py. Пока таблица не реализована.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped["Category"] = relationship(back_populates="clubs")
    leader: Mapped["Leader"] = relationship(back_populates="clubs")
    sessions: Mapped[list["ClubSession"]] = relationship(
        back_populates="club",
        cascade="all, delete-orphan",
    )
