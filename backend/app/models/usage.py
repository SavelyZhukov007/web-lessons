"""Обезличенная статистика (docs/privacy.md). Уровень А: счётчики по дню без идентификаторов.
Уровень Б: активность установки по HMAC(секрет сервера, случайный id), без IP, UA и событий внутри."""

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class UsageBatch(Base):
    """Случайный id пачки для дедупликации повторной отправки (не человек). Хранится 2 дня."""

    __tablename__ = "usage_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)


class UsageDaily(Base):
    """Уровень А: сколько раз за день (МСК) по платформе, каналу и версии. Сырые дни 90 дней, затем usage_monthly."""

    __tablename__ = "usage_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    channel: Mapped[str] = mapped_column(String(1), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    dim: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class UsageMonthly(Base):
    """Свёртка старше 90 дней: месяц, версия не мельче минорной (1.9). Хранится 2 года."""

    __tablename__ = "usage_monthly"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    channel: Mapped[str] = mapped_column(String(1), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    metric: Mapped[str] = mapped_column(String(40), primary_key=True)
    dim: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class PerfDaily(Base):
    """Скорость: значения сразу в корзинах (b1 <1 с, b2 1..2,5 с, b3 2,5..4 с, b4 >4 с; CLS: b1 хорошо .. b3 плохо)."""

    __tablename__ = "perf_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    metric: Mapped[str] = mapped_column(String(16), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(8), primary_key=True)
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


class InstallActivity(Base):
    """Уровень Б: HMAC id установки, неделя первого запуска (first_day), битовая маска активных дней за 120 дней.
    Бит 0 = last_day, бит i = last_day - i дней. Строка удаляется через 120 дней без активности."""

    __tablename__ = "install_activity"
    id_hmac: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), nullable=False)
    channel: Mapped[str] = mapped_column(String(1), nullable=False, default="p")
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    first_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    last_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    days_bits: Mapped[str] = mapped_column(String(32), nullable=False, default="1")  # hex, не больше 120 бит


class RetentionWeekly(Base):
    """Недельные когорты: из size установок недели cohort_week в неделю week_n были активны active. Хранится 2 года."""

    __tablename__ = "retention_weekly"
    cohort_week: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    week_n: Mapped[int] = mapped_column(Integer, primary_key=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[int] = mapped_column(Integer, nullable=False)


class VersionDaily(Base):
    """Принятие обновлений: сколько установок версии были активны в этот день. Хранится 2 года."""

    __tablename__ = "version_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    platform: Mapped[str] = mapped_column(String(12), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    active: Mapped[int] = mapped_column(Integer, nullable=False)
