"""Anonymous daily aggregates: no account, install ID, IP, query or error message."""

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class UsageBatch(Base):
    __tablename__ = "usage_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(16), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class ClientErrorCount(Base):
    __tablename__ = "client_error_counts"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    build: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    line: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
