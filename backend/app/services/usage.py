"""Обезличенная статистика (docs/privacy.md). Включена по умолчанию, в настройках клиента есть выключатель.

Уровень А: счётчики {metric, dim} по дню (МСК), платформе, каналу и версии. Только значения из закрытых списков,
никаких свободных строк. Повтор пачки отсекается случайным batch_id (не человек).
Уровень Б: activity() — HMAC(секрет сервера, случайный id установки), неделя первого запуска и маска активных дней.
Сырые дни хранятся 90 дней, затем сворачиваются в usage_monthly (2 года); install_activity — 120 дней без активности.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .. import settings
from ..models.usage import (
    ClientErrorCount,
    InstallActivity,
    PerfDaily,
    RetentionWeekly,
    UsageBatch,
    UsageDaily,
    UsageMonthly,
    VersionDaily,
)
from .clock import today_msk

RAW_DAYS = 90
MONTHLY_DAYS = 730
ACTIVITY_DAYS = 120
BITS_MASK = (1 << ACTIVITY_DAYS) - 1

METRICS = (
    # запуск, экраны, расписание
    "page_open", "app_open", "app_resume", "screen_view", "schedule_view", "schedule_nav",
    # кружки, поиск, фильтры, календарь, 3D-тур, поделиться
    "club_view", "fav_add", "fav_remove", "search_open", "search_results", "search_pick", "search_abandon", "filter_apply",
    "calendar_export", "calendar_fail", "tour_open", "share", "print",
    # установка PWA, iOS, APK; обновления
    "install_banner", "install_open", "install_download", "install_prompt_available", "install_prompt", "install_accept",
    "install_decline", "installed", "standalone_open", "ios_guide_open", "ios_guide_step", "ios_first_standalone",
    "apk_page", "apk_download", "apk_first_run", "update_offer", "update_accept", "update_later", "update_done",
    # пуши
    "push_shown", "push_open", "push_dismiss", "push_permission", "push_subscribe", "push_unsubscribe",
    # ошибки, офлайн, источник загрузки
    "api_error", "native_crash", "offline_open", "offline_view_stale", "load_source",
    # отзывы
    "fb_prompt_shown", "fb_rating", "fb_prompt_dismiss", "fb_prompt_snooze", "fb_form_open", "fb_sent",
)
Metric = Literal[METRICS]  # type: ignore[valid-type]
_FIXED_DIMS = {
    "none", "other", "online", "offline", "cold", "warm",
    "home", "week", "day", "club", "clubs", "my", "settings", "install", "print", "whats_new", "admin",
    "today", "tomorrow", "day_other", "week_this", "week_next", "week_other", "swipe", "tap", "datepicker",
    "category", "room", "leader", "format", "one", "few", "many", "event",
    "web", "ios", "fcm", "android", "granted", "denied", "default",
    "1", "2", "3", "4", "5", "prompt_usage", "prompt_update", "prompt_error", "shake", "error",
    "cache", "network", "server", "d0", "d1", "d2_7", "d8p", "webview", "ui", "net", "storage",
}
API_ENDPOINTS = ("schedule", "clubs", "club", "reference", "announcements", "push", "feedback", "app", "admin", "other")
API_CLASSES = ("4xx", "5xx", "net")
DIMS = frozenset(_FIXED_DIMS | {f"{e}_{c}" for e in API_ENDPOINTS for c in API_CLASSES} | {f"step{i}" for i in range(1, 9)})
_DIM_PATTERNS = (re.compile(r"^c\d{1,6}$"), re.compile(r"^\d{1,2}\.\d{1,2}\.\d{3}$"))  # id кружка (справочник), версия
PERF_METRICS = ("lcp", "inp", "cls", "ttfb", "fcp", "ttfs")
PERF_BUCKETS = ("b1", "b2", "b3", "b4")
Platform = Literal["web", "pwa", "ios", "android"]
Channel = Literal["p", "i", "l"]
VERSION_RE = r"^(\d{1,2}\.\d{1,2}\.\d{3})?$"


RATE, WINDOW = 600, 600  # пачек с одного IP за 10 минут: за NAT колледжа сидят сотни устройств
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, now: float | None = None) -> bool:
    """Ограничение частоты в памяти процесса; IP нигде не сохраняется."""
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits[key]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= RATE:
            return False
        q.append(now)
        if len(_hits) > 10000:
            for k in [k for k, v in _hits.items() if not v][:5000]:
                _hits.pop(k, None)
        return True


def reset_limits() -> None:
    with _lock:
        _hits.clear()


def valid_dim(value: str) -> bool:
    return value in DIMS or any(p.match(value) for p in _DIM_PATTERNS)


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Metric
    dim: str = Field(default="none", max_length=32)
    bucket: str | None = Field(default=None, max_length=32)  # клиенты v1.9.023 и старше

    @model_validator(mode="after")
    def _closed_list(self):
        if self.bucket is not None and self.dim == "none":
            self.dim = self.bucket
        self.bucket = None
        if not valid_dim(self.dim):
            raise ValueError("dim не из списка")
        return self


class PerfIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal[PERF_METRICS]  # type: ignore[valid-type]
    bucket: Literal[PERF_BUCKETS]  # type: ignore[valid-type]


class ErrorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "URIError", "EvalError", "ResourceError", "UnhandledRejection"
    ]
    source: str = Field(default="unknown", max_length=100, pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    line: int = Field(default=0, ge=0, le=1000000)


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]{32}$")
    platform: Platform
    channel: Channel = "p"
    version: str = Field(default="", max_length=16, pattern=VERSION_RE)
    build: str = Field(default="local", max_length=64, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    events: list[EventIn] = Field(default_factory=list, max_length=50)
    errors: list[ErrorIn] = Field(default_factory=list, max_length=20)
    perf: list[PerfIn] = Field(default_factory=list, max_length=20)


class ActivityIn(BaseModel):
    """Уровень Б (POST /api/app/ping): случайный id установки; сервер хранит только HMAC."""

    model_config = ConfigDict(extra="forbid")
    install_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    kind: str = Field("web", pattern=r"^(web|ios-pwa|pwa|android)$")
    channel: Channel = "p"
    version: str = Field(default="", max_length=16, pattern=VERSION_RE)

    @field_validator("version", mode="before")
    @classmethod
    def _strip_letters(cls, v):
        m = re.match(r"^v?(\d{1,2}\.\d{1,2}\.\d{3})", str(v or ""))
        return m.group(1) if m else ""


def _upsert(db: Session, model, keys: dict, field: str, value: int) -> None:
    stmt = insert(model).values(**keys, **{field: value})
    db.execute(stmt.on_conflict_do_update(index_elements=list(keys), set_={field: getattr(model, field) + value}))


def record(db: Session, body: BatchIn, day: date | None = None):
    day = day or today_msk()
    if not body.events and not body.errors and not body.perf:
        return {"accepted": 0, "duplicate": False}
    claimed = db.execute(insert(UsageBatch).values(id=body.batch_id, day=day).on_conflict_do_nothing()).rowcount
    if not claimed:
        db.rollback()
        return {"accepted": 0, "duplicate": True}
    base = {"day": day, "platform": body.platform, "channel": body.channel, "version": body.version}
    for (metric, dim), count in Counter((e.metric, e.dim) for e in body.events).items():
        _upsert(db, UsageDaily, {**base, "metric": metric, "dim": dim}, "count", count)
    for (metric, bucket), count in Counter((p.metric, p.bucket) for p in body.perf).items():
        _upsert(db, PerfDaily, {"day": day, "platform": body.platform, "version": body.version, "metric": metric, "bucket": bucket},
                "count", count)
    build = body.version or body.build
    for (code, source, line), count in Counter((e.code, e.source, e.line) for e in body.errors).items():
        _upsert(db, ClientErrorCount, {"day": day, "platform": body.platform, "build": build, "code": code, "source": source, "line": line},
                "count", count)
    db.commit()
    return {"accepted": len(body.events) + len(body.errors) + len(body.perf), "duplicate": False}


def count_server(db: Session, metric: str, dim: str = "server", day: date | None = None) -> None:
    """Счётчик, который ведёт сам сервер (отдача APK): без id и без данных запроса."""
    _upsert(db, UsageDaily, {"day": day or today_msk(), "platform": "server", "channel": "p", "version": "", "metric": metric, "dim": dim},
            "count", 1)
    db.commit()


# ---------- уровень Б: активность установки ----------

def activity_key(install_id: str) -> str:
    return hmac.new(settings.jwt_secret().encode(), ("activity|" + install_id).encode(), hashlib.sha256).hexdigest()


def platform_of(kind: str) -> str:
    return {"ios-pwa": "ios", "pwa": "pwa", "android": "android"}.get(kind, "web")


def shift_bits(bits: int, last_day: date, day: date) -> int:
    """Маска с якорем last_day → маска с якорем day (day >= last_day), с отметкой day."""
    delta = (day - last_day).days
    if delta < 0:
        return bits | (1 << -delta) if -delta < ACTIVITY_DAYS else bits
    return ((bits << delta) | 1) & BITS_MASK


def activity(db: Session, body: ActivityIn, day: date | None = None) -> None:
    day = day or today_msk()
    key, platform = activity_key(body.install_id), platform_of(body.kind)
    row = db.get(InstallActivity, key)
    counted = False
    if row is None:
        row = InstallActivity(id_hmac=key, platform=platform, channel=body.channel, version=body.version,
                              first_day=day, last_day=day, days_bits="1")
        db.add(row)
        counted = True
    else:
        bits = int(row.days_bits or "0", 16)
        counted = day > row.last_day or (body.version and body.version != row.version)
        if day >= row.last_day:
            row.days_bits = format(shift_bits(bits, row.last_day, day), "x")
            row.last_day = day
        row.platform, row.channel = platform, body.channel
        if body.version:
            row.version = body.version
    if counted and body.version:
        _upsert(db, VersionDaily, {"day": day, "platform": platform, "version": body.version}, "active", 1)
    db.commit()


def active_on(row: InstallActivity, day: date) -> bool:
    back = (row.last_day - day).days
    return 0 <= back < ACTIVITY_DAYS and bool(int(row.days_bits or "0", 16) >> back & 1)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def compute_retention(db: Session, today: date | None = None) -> int:
    """Недельные когорты за последние 120 дней из масок активности → retention_weekly. Возвращает число строк."""
    today = today or today_msk()
    since = week_start(today - timedelta(days=ACTIVITY_DAYS - 7))
    groups: dict[tuple[date, str], list[InstallActivity]] = {}
    for row in db.scalars(select(InstallActivity).where(InstallActivity.first_day >= since)):
        groups.setdefault((week_start(row.first_day), row.platform), []).append(row)
    written = 0
    for (cohort, platform), rows in groups.items():
        weeks = (week_start(today) - cohort).days // 7
        for n in range(weeks + 1):
            start = cohort + timedelta(days=7 * n)
            active = sum(1 for r in rows if any(active_on(r, start + timedelta(days=d)) for d in range(7) if start + timedelta(days=d) <= today))
            stmt = insert(RetentionWeekly).values(cohort_week=cohort, platform=platform, week_n=n, size=len(rows), active=active)
            db.execute(stmt.on_conflict_do_update(index_elements=["cohort_week", "platform", "week_n"],
                                                  set_={"size": len(rows), "active": active}))
            written += 1
    db.commit()
    return written


def day_retention(rows: list[InstallActivity], today: date) -> dict:
    """D1/D7/D30: доля установок, активных ровно через 1/7/30 дней после первого дня (только созревшие когорты)."""
    out = {}
    for n in (1, 7, 30):
        mature = [r for r in rows if r.first_day + timedelta(days=n) <= today]
        kept = sum(1 for r in mature if active_on(r, r.first_day + timedelta(days=n)))
        out[f"d{n}"] = {"cohort": len(mature), "kept": kept, "rate": round(kept / len(mature), 3) if mature else None}
    return out


# ---------- хранение: 90 дней сырых, потом месяцы ----------

def minor(version: str) -> str:
    m = re.match(r"^(\d+\.\d+)", version or "")
    return m.group(1) if m else ""


def rollup(db: Session, today: date | None = None) -> dict:
    """Свёртка старше 90 дней в usage_monthly и удаление сырых строк; чистка по срокам хранения. Идемпотентна."""
    today = today or today_msk()
    edge = today - timedelta(days=RAW_DAYS - 1)
    moved = 0
    for row in db.scalars(select(UsageDaily).where(UsageDaily.day < edge)).all():
        _upsert(db, UsageMonthly, {"month": row.day.strftime("%Y-%m"), "platform": row.platform, "channel": row.channel,
                                   "version": minor(row.version), "metric": row.metric, "dim": row.dim}, "count", row.count)
        moved += 1
    for row in db.scalars(select(PerfDaily).where(PerfDaily.day < edge)).all():
        _upsert(db, UsageMonthly, {"month": row.day.strftime("%Y-%m"), "platform": row.platform, "channel": "p",
                                   "version": minor(row.version), "metric": "perf_" + row.metric, "dim": row.bucket}, "count", row.count)
        moved += 1
    for row in db.scalars(select(ClientErrorCount).where(ClientErrorCount.day < edge)).all():
        _upsert(db, UsageMonthly, {"month": row.day.strftime("%Y-%m"), "platform": row.platform, "channel": "p",
                                   "version": minor(row.build), "metric": "js_error", "dim": row.code[:32]}, "count", row.count)
        moved += 1
    for model in (UsageDaily, PerfDaily, ClientErrorCount):
        db.execute(delete(model).where(model.day < edge))
    db.execute(delete(UsageBatch).where(UsageBatch.day < today - timedelta(days=2)))
    keep_from = today - timedelta(days=MONTHLY_DAYS)
    db.execute(delete(UsageMonthly).where(UsageMonthly.month < keep_from.strftime("%Y-%m")))
    db.execute(delete(RetentionWeekly).where(RetentionWeekly.cohort_week < keep_from))
    db.execute(delete(VersionDaily).where(VersionDaily.day < keep_from))
    gone = db.execute(delete(InstallActivity).where(InstallActivity.last_day < today - timedelta(days=ACTIVITY_DAYS))).rowcount
    db.commit()
    return {"rolled_up": moved, "forgotten_installs": gone or 0}


def cleanup(db: Session, *, commit=True):
    """Ночная задача: свёртка, сроки хранения, пересчёт когорт."""
    result = rollup(db)
    compute_retention(db)
    return result


def summary(db: Session):
    """Краткая сводка для «Обзора» (30 дней)."""
    since = today_msk() - timedelta(days=29)
    counts = db.execute(
        select(UsageDaily.metric, UsageDaily.dim, func.sum(UsageDaily.count))
        .where(UsageDaily.day >= since)
        .group_by(UsageDaily.metric, UsageDaily.dim)
    ).all()
    platforms = db.execute(
        select(UsageDaily.platform, func.sum(UsageDaily.count)).where(UsageDaily.day >= since).group_by(UsageDaily.platform)
    ).all()
    errors = db.execute(
        select(
            ClientErrorCount.platform,
            ClientErrorCount.build,
            ClientErrorCount.code,
            ClientErrorCount.source,
            ClientErrorCount.line,
            func.sum(ClientErrorCount.count).label("count"),
        )
        .where(ClientErrorCount.day >= since)
        .group_by(ClientErrorCount.platform, ClientErrorCount.build, ClientErrorCount.code, ClientErrorCount.source, ClientErrorCount.line)
        .order_by(func.sum(ClientErrorCount.count).desc())
        .limit(20)
    ).all()
    return {
        "since": str(since),
        "retention_days": RAW_DAYS,
        "events": [{"metric": m, "bucket": b, "count": n} for m, b, n in counts],
        "platforms": dict(platforms),
        "errors": [dict(row._mapping) for row in errors],
    }
