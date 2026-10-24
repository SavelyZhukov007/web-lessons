"""«Сегодня» по московскому времени, а не по TZ сервера (API-07). Нужен пакет tzdata на Windows/минимальных образах."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    MSK = ZoneInfo("Europe/Moscow")
except Exception:  # noqa: BLE001 — нет tzdata: Москва без перехода на летнее время с 2014 г. = UTC+3
    MSK = timezone(timedelta(hours=3), "MSK")


def now_msk() -> datetime:
    return datetime.now(MSK)


def today_msk() -> date:
    return now_msk().date()
