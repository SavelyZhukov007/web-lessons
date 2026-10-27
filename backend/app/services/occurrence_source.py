"""Единая точка «реальных дат» занятий (schedule v2, контракт: docs/schedule-v2-contract.md).

Все потребители (неделя, .ics, конфликты, уведомления, публикация импорта) берут даты
только отсюда. Источник базовых дат:

* если импортируется ``backend.app.services.occurrences`` (T1) и в нём есть
  ``load_calendar(db)`` и ``session_dates(session, date_from, date_to, calendar)`` —
  используются они (учебные периоды, чётность, неучебные дни, repeat);
* иначе — встроенный fallback: weekly по ``weekday`` / разово по ``one_off_date``;
  если в БД уже есть таблицы ``academic_periods``/``no_class_days`` и колонка
  ``sessions.repeat`` — fallback учитывает и их (та же семантика, что в контракте).

Исключения (отмена/перенос) адаптер применяет сам в обоих режимах.
Ведущие и аудитории: ``session_leaders`` → ``club_leaders`` → ``clubs.leader_id``;
``session_rooms`` → ``sessions.room_id`` (таблицы T2 подхватываются, если существуют).
"""
from __future__ import annotations

import importlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Iterable, Protocol

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .clock import today_msk

OCCUPYING = frozenset({"scheduled", "moved_in"})
REPEAT_VALUES = ("weekly", "even", "odd", "once")
DEFAULT_HORIZON_WEEKS = 26


# --------------------------------------------------------------------------- модели


@dataclass(frozen=True)
class Occurrence:
    date: date
    start: str
    end: str
    room_ids: tuple[int, ...]
    leader_ids: tuple[int, ...]
    status: str  # scheduled | moved_in | moved_out | cancelled
    source_session_id: int
    exception_id: int | None = None
    original_date: date | None = None
    club_id: int | None = None
    parity: str | None = None  # odd | even | None (нет учебного периода)
    comment: str = ""
    original_start: str | None = None
    original_end: str | None = None
    group_ids: tuple[str, ...] = ()

    @property
    def occupies(self) -> bool:
        return self.status in OCCUPYING

    @property
    def key(self) -> str:
        """Стабильный id occurrence: «session_id:исходная дата» (как event_id недели)."""
        return f"{self.source_session_id}:{(self.original_date or self.date).isoformat()}"


@dataclass(frozen=True)
class Period:
    id: int | None
    title: str
    starts_on: date
    ends_on: date
    anchor_week: date  # понедельник
    anchor_parity: str  # odd | even


class CalendarLike(Protocol):
    def period_for(self, day: date) -> Any: ...
    def parity(self, day: date) -> str | None: ...
    def is_no_class(self, day: date) -> bool: ...


@dataclass
class FallbackCalendar:
    periods: list[Period] = field(default_factory=list)
    no_class: dict[date, str] = field(default_factory=dict)

    def period_for(self, day: date) -> Period | None:
        for period in self.periods:
            if period.starts_on <= day <= period.ends_on:
                return period
        return None

    def parity(self, day: date) -> str | None:
        period = self.period_for(day)
        if period is None:
            return None
        monday = day - timedelta(days=day.weekday())
        shift = ((monday - period.anchor_week).days // 7) % 2
        if shift == 0:
            return period.anchor_parity
        return "even" if period.anchor_parity == "odd" else "odd"

    def is_no_class(self, day: date) -> bool:
        return day in self.no_class

    def no_class_title(self, day: date) -> str | None:
        return self.no_class.get(day)


# --------------------------------------------------------------------------- провайдер


class _FallbackProvider:
    name = "fallback"

    @staticmethod
    def load_calendar(db: Session) -> FallbackCalendar:
        tables = _tables(db)
        cal = FallbackCalendar()
        if "academic_periods" in tables:
            cols = _columns(db, "academic_periods")
            where = " WHERE is_active = 1" if "is_active" in cols else ""
            for row in db.execute(text(f"SELECT * FROM academic_periods{where}")).mappings():
                starts = _d(row["starts_on"])
                anchor = _d(row.get("anchor_week") or starts)
                cal.periods.append(
                    Period(
                        id=row.get("id"),
                        title=str(row.get("title") or ""),
                        starts_on=starts,
                        ends_on=_d(row["ends_on"]),
                        anchor_week=anchor - timedelta(days=anchor.weekday()),
                        anchor_parity=str(row.get("anchor_parity") or "odd"),
                    )
                )
            cal.periods.sort(key=lambda p: p.starts_on)
        if "no_class_days" in tables:
            for row in db.execute(text("SELECT * FROM no_class_days")).mappings():
                cal.no_class[_d(row["date"])] = str(row.get("title") or "")
        return cal

    @staticmethod
    def session_dates(session: Any, date_from: date, date_to: date, calendar: Any) -> list[date]:
        repeat = session_repeat(session)
        no_class = getattr(calendar, "is_no_class", lambda _d: False)
        if repeat == "once":
            one = getattr(session, "one_off_date", None)
            if not one:
                return []
            day = _d(one)
            return [day] if date_from <= day <= date_to and not no_class(day) else []
        periods = getattr(calendar, "periods", None)
        result: list[date] = []
        weekday = int(session.weekday)
        first = date_from + timedelta(days=(weekday - date_from.isoweekday()) % 7)
        day = first
        while day <= date_to:
            if no_class(day):
                pass
            elif periods and calendar.period_for(day) is None:
                pass  # периоды заданы — вне периода занятий нет
            elif repeat in ("even", "odd"):
                if calendar.parity(day) == repeat:
                    result.append(day)
            else:
                result.append(day)
            day += timedelta(days=7)
        return result


class _T1Calendar(FallbackCalendar):
    """Календарь T1: периоды academic_periods (name/start_date/end_date/even_week_start) и
    неучебные дни по периодам. Чётность: неделя even_week_start — чётная."""

    def __init__(self, periods, holidays, raw):
        super().__init__(periods=periods, no_class={})
        self.holidays = holidays  # period_id -> {date: reason}
        self.raw = raw  # period_id -> dict для services.occurrences.original_occurs
        for days in holidays.values():
            self.no_class.update(days)

    def is_no_class(self, day: date) -> bool:
        period = self.period_for(day)
        return period is not None and day in self.holidays.get(period.id, {})


class _T1Provider:
    """Делегирует правило «есть ли занятие в этот день» в services.occurrences.original_occurs (T1)."""

    name = "occurrences"

    @staticmethod
    def load_calendar(db: Session):
        tables = _tables(db)
        periods, raw, holidays = [], {}, {}
        if "academic_periods" in tables:
            for row in db.execute(text("SELECT * FROM academic_periods")).mappings():
                anchor = _d(row["even_week_start"])
                periods.append(Period(id=row["id"], title=str(row.get("name") or ""), starts_on=_d(row["start_date"]),
                                      ends_on=_d(row["end_date"]), anchor_week=anchor - timedelta(days=anchor.weekday()),
                                      anchor_parity="even"))
                raw[row["id"]] = {"id": row["id"], "start_date": str(row["start_date"])[:10],
                                  "end_date": str(row["end_date"])[:10], "even_week_start": str(row["even_week_start"])[:10]}
        if "no_class_days" in tables:
            for row in db.execute(text("SELECT * FROM no_class_days")).mappings():
                holidays.setdefault(row["period_id"], {})[_d(row["date"])] = str(row.get("reason") or "")
        periods.sort(key=lambda p: p.starts_on)
        return _T1Calendar(periods, holidays, raw)

    @staticmethod
    def session_dates(session: Any, date_from: date, date_to: date, calendar: Any) -> list[date]:
        from . import occurrences as t1

        pid = getattr(session, "period_id", None)
        period = getattr(calendar, "raw", {}).get(pid) if pid is not None else None
        holidays = {d.isoformat() for d in getattr(calendar, "holidays", {}).get(pid, {})}
        payload = {"weekday": int(session.weekday), "one_off_date": getattr(session, "one_off_date", None),
                   "repeat": getattr(session, "repeat", None) or "weekly"}
        weekday = int(session.weekday)
        day = date_from + timedelta(days=(weekday - date_from.isoweekday()) % 7)
        out = []
        while day <= date_to:
            if t1.original_occurs(payload, day, period, holidays):
                out.append(day)
            day += timedelta(days=7)
        return out


_provider_override: Any = None


def set_provider(provider: Any) -> None:
    """Тесты/инструменты: подменить источник базовых дат (None — вернуть автоопределение)."""
    global _provider_override
    _provider_override = provider


def get_provider() -> Any:
    if _provider_override is not None:
        return _provider_override
    try:
        module = importlib.import_module("backend.app.services.occurrences")
    except Exception:  # noqa: BLE001 — T1 не влит
        return _FallbackProvider
    if callable(getattr(module, "load_calendar", None)) and callable(getattr(module, "session_dates", None)):
        return module
    if callable(getattr(module, "original_occurs", None)):
        return _T1Provider
    return _FallbackProvider


def provider_name() -> str:
    provider = get_provider()
    return getattr(provider, "name", None) or getattr(provider, "__name__", "provider")


# --------------------------------------------------------------------------- снимок данных


@dataclass
class Snapshot:
    """Состояние расписания в памяти: на нём же симулируются предлагаемые изменения."""

    sessions: dict[int, SimpleNamespace]
    exceptions: list[SimpleNamespace]
    clubs: dict[int, SimpleNamespace]
    rooms: dict[int, SimpleNamespace]
    leaders: dict[int, SimpleNamespace]
    categories: dict[int, SimpleNamespace]
    club_leaders: dict[int, tuple[int, ...]]
    session_leaders: dict[int, tuple[int, ...]]
    session_rooms: dict[int, tuple[int, ...]]
    session_groups: dict[int, tuple[str, ...]]
    calendar: Any

    def copy(self) -> "Snapshot":
        def clone(ns: SimpleNamespace) -> SimpleNamespace:
            return SimpleNamespace(**vars(ns))

        return Snapshot(
            sessions={k: clone(v) for k, v in self.sessions.items()},
            exceptions=[clone(e) for e in self.exceptions],
            clubs={k: clone(v) for k, v in self.clubs.items()},
            rooms=self.rooms,
            leaders=self.leaders,
            categories=self.categories,
            club_leaders=dict(self.club_leaders),
            session_leaders=dict(self.session_leaders),
            session_rooms=dict(self.session_rooms),
            session_groups=dict(self.session_groups),
            calendar=self.calendar,
        )

    def exceptions_by_session(self) -> dict[int, list[SimpleNamespace]]:
        grouped: dict[int, list[SimpleNamespace]] = defaultdict(list)
        for exc in self.exceptions:
            grouped[exc.session_id].append(exc)
        return grouped


def _tables(db: Session) -> set[str]:
    return set(inspect(db.get_bind()).get_table_names())


def _columns(db: Session, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _rows(db: Session, table: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(f"SELECT * FROM {table}")).mappings()]


def _pairs(db: Session, tables: set[str], table: str, key: str, value: str) -> dict[int, tuple]:
    if table not in tables:
        return {}
    cols = _columns(db, table)
    if key not in cols or value not in cols:
        return {}
    order = " ORDER BY position" if "position" in cols else ""
    grouped: dict[int, list] = defaultdict(list)
    for row in db.execute(text(f"SELECT {key}, {value} FROM {table}{order}")).all():
        if row[1] not in grouped[row[0]]:
            grouped[row[0]].append(row[1])
    return {k: tuple(v) for k, v in grouped.items()}


def load_snapshot(db: Session) -> Snapshot:
    db.flush()
    tables = _tables(db)
    ns = lambda rows: {r["id"]: SimpleNamespace(**r) for r in rows}  # noqa: E731
    return Snapshot(
        sessions=ns(_rows(db, "sessions")),
        exceptions=[SimpleNamespace(**r) for r in _rows(db, "session_exceptions")],
        clubs=ns(_rows(db, "clubs")),
        rooms=ns(_rows(db, "rooms")),
        leaders=ns(_rows(db, "leaders")),
        categories=ns(_rows(db, "categories")),
        club_leaders=_pairs(db, tables, "club_leaders", "club_id", "leader_id"),
        session_leaders=_pairs(db, tables, "session_leaders", "session_id", "leader_id"),
        session_rooms=_pairs(db, tables, "session_rooms", "session_id", "room_id"),
        session_groups=_pairs(db, tables, "session_groups", "session_id", "group_code"),
        calendar=get_provider().load_calendar(db),
    )


# --------------------------------------------------------------------------- вычисление


def session_repeat(session: Any) -> str:
    # как services.occurrences.original_occurs: дата one_off_date важнее поля repeat
    if getattr(session, "one_off_date", None):
        return "once"
    value = getattr(session, "repeat", None)
    if value in REPEAT_VALUES:
        return value
    return "once" if getattr(session, "one_off_date", None) else "weekly"


def repeat_label(session: Any) -> str:
    repeat = session_repeat(session)
    if repeat == "once":
        one = getattr(session, "one_off_date", None)
        return f"разово {_d(one):%d.%m.%Y}" if one else "разово"
    return {"weekly": "каждую неделю", "even": "по чётным неделям", "odd": "по нечётным неделям"}[repeat]


def leaders_of(snap: Snapshot, session: Any) -> tuple[int, ...]:
    """Как ClubSession.leader_ids / Club.leader_ids (T2): ведущие занятия, иначе основной ведущий кружка + доп."""
    if snap.session_leaders.get(session.id):
        return tuple(sorted(snap.session_leaders[session.id]))
    club = snap.clubs.get(session.club_id)
    leader_id = getattr(club, "leader_id", None) if club else None
    extra = sorted(set(snap.club_leaders.get(session.club_id, ())) - {leader_id})
    return tuple(([leader_id] if leader_id is not None else []) + extra)


def rooms_of(snap: Snapshot, session: Any) -> tuple[int, ...]:
    """Как ClubSession.room_ids (T2): основная аудитория первой, затем доп. из session_rooms."""
    main = getattr(session, "room_id", None)
    extra = sorted(set(snap.session_rooms.get(session.id, ())) - {main})
    return tuple(([main] if main is not None else []) + extra)


def room_is_remote(snap: Snapshot, room_id: int) -> bool:
    room = snap.rooms.get(room_id)
    return bool(getattr(room, "is_remote", False)) if room else False


def _parity(calendar: Any, day: date) -> str | None:
    fn = getattr(calendar, "parity", None)
    try:
        return fn(day) if fn else None
    except Exception:  # noqa: BLE001
        return None


def snapshot_occurrences(
    snap: Snapshot,
    date_from: date,
    date_to: date,
    *,
    session_ids: Iterable[int] | None = None,
    include_inactive: bool = False,
) -> list[Occurrence]:
    provider = get_provider()
    wanted = set(session_ids) if session_ids is not None else None
    by_session = snap.exceptions_by_session()
    result: list[Occurrence] = []
    for sid, session in snap.sessions.items():
        if wanted is not None and sid not in wanted:
            continue
        club = snap.clubs.get(session.club_id)
        if club is None or (not include_inactive and not getattr(club, "is_active", True)):
            continue
        result.extend(_session_occurrences(snap, provider, session, by_session.get(sid, []), date_from, date_to))
    result.sort(key=lambda o: (o.date, o.start, o.source_session_id))
    return result


def _session_occurrences(snap, provider, session, exceptions, date_from, date_to) -> list[Occurrence]:
    base_dates = set(provider.session_dates(session, date_from, date_to, snap.calendar))
    rooms = rooms_of(snap, session)
    leaders = leaders_of(snap, session)
    groups = snap.session_groups.get(session.id, ())
    by_original = {_d(e.original_date): e for e in exceptions}
    out: list[Occurrence] = []
    common = dict(
        leader_ids=leaders,
        source_session_id=session.id,
        club_id=session.club_id,
        group_ids=groups,
    )
    for day in sorted(base_dates):
        exc = by_original.get(day)
        status = "scheduled"
        comment = ""
        if exc is not None:
            status = "cancelled" if exc.type == "cancelled" else "moved_out"
            comment = exc.comment or ""
        out.append(
            Occurrence(
                date=day,
                start=session.start_time,
                end=session.end_time,
                room_ids=rooms,
                status=status,
                exception_id=getattr(exc, "id", None) if exc is not None else None,
                original_date=day,
                parity=_parity(snap.calendar, day),
                comment=comment,
                **common,
            )
        )
    for exc in exceptions:
        if exc.type != "moved" or not exc.new_date:
            continue
        new_day = _d(exc.new_date)
        if not date_from <= new_day <= date_to:
            continue
        out.append(
            Occurrence(
                date=new_day,
                start=exc.new_start_time,
                end=exc.new_end_time,
                room_ids=(exc.new_room_id,),
                status="moved_in",
                exception_id=getattr(exc, "id", None),
                original_date=_d(exc.original_date),
                parity=_parity(snap.calendar, new_day),
                comment=exc.comment or "",
                original_start=session.start_time,
                original_end=session.end_time,
                **common,
            )
        )
    return out


def is_base_date(snap: Snapshot, session: Any, day: date) -> bool:
    """День — реальная (до исключений) дата серии: для валидации отмен/переносов и уведомлений."""
    return day in set(get_provider().session_dates(session, day, day, snap.calendar))


# --------------------------------------------------------------------------- публичный API


def iter_occurrences(db: Session, session: Any, date_from: date, date_to: date) -> list[Occurrence]:
    """Контрактная точка входа: occurrences одной серии (вкл. moved_out/cancelled) в окне."""
    snap = load_snapshot(db)
    sid = session if isinstance(session, int) else session.id
    return snapshot_occurrences(snap, date_from, date_to, session_ids=[sid], include_inactive=True)


def default_window(snap: Snapshot | None = None, *, today: date | None = None) -> tuple[date, date]:
    """Окно по умолчанию: сегодня … конец текущего периода, но не меньше 26 недель."""
    start = today or today_msk()
    end = start + timedelta(weeks=DEFAULT_HORIZON_WEEKS)
    if snap is not None:
        period = _period_for(snap.calendar, start)
        ends_on = getattr(period, "ends_on", None) if period is not None else None
        if ends_on is not None and _d(ends_on) > end:
            end = _d(ends_on)
    return start, end


def _period_for(calendar: Any, day: date):
    fn = getattr(calendar, "period_for", None)
    try:
        return fn(day) if fn else None
    except Exception:  # noqa: BLE001
        return None


def period_info(snap: Snapshot, day: date) -> dict | None:
    period = _period_for(snap.calendar, day)
    if period is None:
        return None
    return {
        "id": getattr(period, "id", None),
        "title": getattr(period, "title", ""),
        "starts_on": _d(period.starts_on).isoformat(),
        "ends_on": _d(period.ends_on).isoformat(),
    }


def no_class_in(snap: Snapshot, date_from: date, date_to: date) -> list[dict]:
    cal = snap.calendar
    is_nc = getattr(cal, "is_no_class", None)
    if is_nc is None:
        return []
    title_fn = getattr(cal, "no_class_title", lambda _d: "")
    out = []
    day = date_from
    while day <= date_to:
        if is_nc(day):
            out.append({"date": day.isoformat(), "title": title_fn(day) or ""})
        day += timedelta(days=1)
    return out


def next_dates(snap: Snapshot, session_id: int, *, limit: int = 3, today: date | None = None) -> list[str]:
    start, end = default_window(snap, today=today)
    occs = snapshot_occurrences(snap, start, end, session_ids=[session_id])
    return [o.date.isoformat() for o in occs if o.occupies][:limit]


def has_upcoming(snap: Snapshot, session_id: int, *, today: date | None = None) -> bool:
    return bool(next_dates(snap, session_id, limit=1, today=today))


def week_events(snap: Snapshot, week_start: date) -> list[dict]:
    """События недели в формате ScheduleEvent (совместимо с build_week + поля v2)."""
    week_end = week_start + timedelta(days=6)
    events: list[dict] = []
    for occ in snapshot_occurrences(snap, week_start, week_end):
        if occ.status == "moved_out":
            continue
        event = occurrence_event(snap, occ)
        if event is not None:
            events.append(event)
    events.sort(key=lambda e: (e["date"], e["start_time"], e["club_name"]))
    return events


def occurrence_event(snap: Snapshot, occ: Occurrence) -> dict | None:
    club = snap.clubs.get(occ.club_id)
    if club is None:
        return None
    category = snap.categories.get(club.category_id)
    leader_names = [snap.leaders[i].name for i in occ.leader_ids if i in snap.leaders]
    # формат T2 (services.schedule._location_payload): «аудитория · корпус», дистант не занимает аудиторию
    room_names = [" · ".join(filter(None, [snap.rooms[i].name, getattr(snap.rooms[i], "building", None)]))
                  for i in occ.room_ids if i in snap.rooms]
    session = snap.sessions.get(occ.source_session_id)
    status = {"moved_in": "moved"}.get(occ.status, occ.status)
    event = {
        "event_id": occ.key,
        "session_id": occ.source_session_id,
        "club_id": club.id,
        "club_name": club.name,
        "category_id": getattr(category, "id", club.category_id),
        "category_name": getattr(category, "name", ""),
        "category_color": getattr(category, "color", ""),
        "leader_id": occ.leader_ids[0] if occ.leader_ids else getattr(club, "leader_id", 0),
        "leader_name": leader_names[0] if leader_names else "",
        "room_id": occ.room_ids[0] if occ.room_ids else 0,
        "room_name": snap.rooms[occ.room_ids[0]].name if occ.room_ids and occ.room_ids[0] in snap.rooms else "",
        "date": occ.date.isoformat(),
        "start_time": occ.start,
        "end_time": occ.end,
        "status": status,
        "original_date": (occ.original_date or occ.date).isoformat(),
        "comment": occ.comment,
        "parity": occ.parity,
        "room_ids": list(occ.room_ids),
        "leader_ids": list(occ.leader_ids),
        "leader_names": leader_names,
        "room_names": room_names,
        "occupied_room_ids": [i for i in occ.room_ids if not room_is_remote(snap, i)],
        "is_remote": bool(occ.room_ids) and all(room_is_remote(snap, i) for i in occ.room_ids),
        "repeat": session_repeat(session) if session is not None else "weekly",
        "period_id": getattr(session, "period_id", None) if session is not None else None,
    }
    if occ.status == "moved_in":
        event["original_start_time"] = occ.original_start
        event["original_end_time"] = occ.original_end
    return event


def occurrence_dict(occ: Occurrence) -> dict:
    return {
        "key": occ.key,
        "date": occ.date.isoformat(),
        "start": occ.start,
        "end": occ.end,
        "status": occ.status,
        "session_id": occ.source_session_id,
        "club_id": occ.club_id,
        "room_ids": list(occ.room_ids),
        "leader_ids": list(occ.leader_ids),
        "exception_id": occ.exception_id,
        "original_date": (occ.original_date or occ.date).isoformat(),
        "parity": occ.parity,
        "comment": occ.comment,
    }


def _d(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


__all__ = [
    "Occurrence",
    "Snapshot",
    "FallbackCalendar",
    "Period",
    "OCCUPYING",
    "iter_occurrences",
    "load_snapshot",
    "snapshot_occurrences",
    "week_events",
    "occurrence_event",
    "occurrence_dict",
    "next_dates",
    "has_upcoming",
    "is_base_date",
    "default_window",
    "period_info",
    "no_class_in",
    "repeat_label",
    "session_repeat",
    "set_provider",
    "get_provider",
    "provider_name",
    "leaders_of",
    "rooms_of",
    "room_is_remote",
]


# --------------------------------------------------------------------------- уведомления


def exception_is_notifiable(snap: Snapshot, exc: Any, *, today: date | None = None) -> bool:
    """Пуш об отмене/переносе шлём, только если исходная дата — реальное занятие серии
    (не неучебный день, не «чужая» неделя чётности, не вне периода), клуб активен и
    затронутая дата (исходная или новая) ещё не прошла."""
    today = today or today_msk()
    session = snap.sessions.get(exc.session_id)
    if session is None:
        return False
    club = snap.clubs.get(session.club_id)
    if club is None or not getattr(club, "is_active", True):
        return False
    original = _d(exc.original_date)
    if not is_base_date(snap, session, original):
        return False
    latest = max([original] + ([_d(exc.new_date)] if getattr(exc, "new_date", None) else []))
    return latest >= today


def reminder_targets(snap: Snapshot, day: date) -> list[Occurrence]:
    """Кому напоминать в день ``day``: только реально идущие занятия (scheduled/moved_in)."""
    return [o for o in snapshot_occurrences(snap, day, day) if o.occupies]


def sessions_without_upcoming(snap: Snapshot, session_ids: Iterable[int], *, today: date | None = None) -> list[int]:
    return [sid for sid in session_ids if sid in snap.sessions and not has_upcoming(snap, sid, today=today)]
