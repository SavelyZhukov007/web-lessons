from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AcademicPeriod(Base):
    __tablename__ = "academic_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    even_week_start: Mapped[str] = mapped_column(String(10))


class NoClassDay(Base):
    __tablename__ = "no_class_days"
    __table_args__ = (UniqueConstraint("period_id", "date", name="uq_no_class_period_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("academic_periods.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(255), default="")
