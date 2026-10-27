from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models.assignments import ClubLeader, SessionLeader
from ..models.category import Category
from ..models.club import Club
from ..models.leader import Leader
from ..models.period import AcademicPeriod, NoClassDay
from ..models.room import Room
from ..models.session import ClubSession
from ..models.session_exception import SessionException
from ..schemas.category import CategoryRead
from ..schemas.club import ClubDetailRead, ClubRead
from ..schemas.contracts import ScheduleEvent
from ..schemas.leader import LeaderPublic, LeaderRead
from ..schemas.room import RoomRead
from ..schemas.session import SessionWithRoomRead
from ..schemas.session_exception import SessionExceptionRead
from ..services import occurrence_source as occ_src
from ..services.calendar_export import build_calendar, build_club_calendar
from ..services.clock import now_msk
from ..services.occurrences import occurrences_for_range
from ..services.schedule import build_week

router = APIRouter(prefix="/api", tags=["public"])


MIN_WEEK = date(2000, 1, 3)
MAX_WEEK = date(2100, 12, 27)
_DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_WEEK_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _parse_week_start(value: str) -> date:
    # API-05/06: строгий формат (на Python ≥3.11 fromisoformat принимает «20261019» и «2026-W43-1») и ограниченный диапазон
    if not _WEEK_RE.fullmatch(value):
        raise HTTPException(422, "week должен иметь формат YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "week должен иметь формат YYYY-MM-DD") from exc
    if not MIN_WEEK <= parsed <= MAX_WEEK:
        raise HTTPException(422, f"week вне допустимого диапазона ({MIN_WEEK}…{MAX_WEEK})")
    if parsed.isoweekday() != 1:
        raise HTTPException(
            422, "week должен указывать на понедельник выбранной недели"
        )
    return parsed


def _dump_schedule_data(db: Session) -> dict:
    return {
        "periods": [{"id": p.id, "name": p.name, "start_date": p.start_date, "end_date": p.end_date, "even_week_start": p.even_week_start} for p in db.scalars(select(AcademicPeriod))],
        "no_class_days": [{"period_id": d.period_id, "date": d.date, "reason": d.reason} for d in db.scalars(select(NoClassDay))],
        "categories": [
            CategoryRead.model_validate(item).model_dump(mode="json")
            for item in db.scalars(select(Category).order_by(Category.id))
        ],
        "leaders": [
            LeaderRead.model_validate(item).model_dump(mode="json")
            for item in db.scalars(select(Leader).order_by(Leader.id))
        ],
        "rooms": [
            RoomRead.model_validate(item).model_dump(mode="json")
            for item in db.scalars(select(Room).order_by(Room.id))
        ],
        "clubs": [
            ClubRead.model_validate(item).model_dump(mode="json")
            for item in db.scalars(select(Club).order_by(Club.id))
        ],
        "sessions": [
            SessionWithRoomRead.model_validate(item).model_dump(
                mode="json", exclude={"room"}
            )
            for item in db.scalars(select(ClubSession).order_by(ClubSession.id))
        ],
        "session_exceptions": [
            SessionExceptionRead.model_validate(item).model_dump(mode="json")
            for item in db.scalars(
                select(SessionException).order_by(SessionException.id)
            )
        ],
    }


@router.get("/periods/week")
def week_periods(week: str, db: Session = Depends(get_db)):
    start = _parse_week_start(week)
    end = start + timedelta(days=6)
    result = []
    for period in db.scalars(select(AcademicPeriod).where(AcademicPeriod.start_date <= end.isoformat(), AcademicPeriod.end_date >= start.isoformat()).order_by(AcademicPeriod.start_date)):
        anchor = date.fromisoformat(period.even_week_start)
        result.append({"id": period.id, "name": period.name, "status": "active", "start_date": period.start_date,
                       "end_date": period.end_date, "parity": "even" if ((start - anchor).days // 7) % 2 == 0 else "odd",
                       "no_class_days": [{"date": day.date, "reason": day.reason} for day in db.scalars(select(NoClassDay).where(NoClassDay.period_id == period.id, NoClassDay.date >= start.isoformat(), NoClassDay.date <= end.isoformat()))]})
    if not result:
        upcoming = db.scalar(select(AcademicPeriod).where(AcademicPeriod.start_date > end.isoformat()).order_by(AcademicPeriod.start_date).limit(1))
        previous = db.scalar(select(AcademicPeriod).where(AcademicPeriod.end_date < start.isoformat()).order_by(AcademicPeriod.end_date.desc()).limit(1))
        period = upcoming or previous
        if period:
            result.append({"id": period.id, "name": period.name, "status": "upcoming" if upcoming else "ended", "start_date": period.start_date, "end_date": period.end_date, "no_class_days": []})
    return result


@router.get("/categories", response_model=list[CategoryRead])
def categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name, Category.id)))


@router.get("/leaders", response_model=list[LeaderPublic])
def leaders(db: Session = Depends(get_db)):
    """Только руководители активных кружков и без контактов (SEC-07)."""
    active = select(Club.leader_id).where(Club.is_active.is_(True)).union(
        select(ClubLeader.leader_id).join(Club, Club.id == ClubLeader.club_id).where(Club.is_active.is_(True)),
        select(SessionLeader.leader_id).join(ClubSession, ClubSession.id == SessionLeader.session_id).join(Club, Club.id == ClubSession.club_id).where(Club.is_active.is_(True)))
    return list(
        db.scalars(select(Leader).where(Leader.id.in_(active)).order_by(Leader.name, Leader.id))
    )


@router.get("/rooms", response_model=list[RoomRead])
def rooms(db: Session = Depends(get_db)):
    return list(db.scalars(select(Room).order_by(Room.building, Room.name, Room.id)))


@router.get("/clubs", response_model=list[ClubRead])
def clubs(
    search: str | None = Query(None, max_length=200),
    category_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
):
    statement = select(Club).where(Club.is_active.is_(True))
    if category_id is not None:
        statement = statement.where(Club.category_id == category_id)
    items = list(db.scalars(statement.order_by(Club.name, Club.id)))
    if search and search.strip():
        # API-01: SQLite LIKE не знает регистр кириллицы, а % и _ работали как маски → ищем в Python по casefold
        needle = search.strip().casefold()
        items = [c for c in items if needle in c.name.casefold() or needle in c.description.casefold()]
    return items


@router.get("/clubs/{club_id}", response_model=ClubDetailRead)
def club(club_id: int, db: Session = Depends(get_db)):
    item = db.scalar(
        select(Club)
        .where(Club.id == club_id, Club.is_active.is_(True))
        .options(
            selectinload(Club.category),
            selectinload(Club.leader),
            selectinload(Club.sessions).selectinload(ClubSession.room),
            selectinload(Club.sessions).selectinload(ClubSession.exceptions),
        )
    )
    if item is None:
        raise HTTPException(404, "Кружок не найден")

    sessions = sorted(
        item.sessions, key=lambda row: (row.weekday, row.start_time, row.id)
    )
    today = now_msk().date().isoformat()
    today_date = date.fromisoformat(today)
    data = _dump_schedule_data(db)
    upcoming_events = occurrences_for_range(today_date, min(date.max - timedelta(days=7), today_date + timedelta(days=55)), data, item.id)
    upcoming_exceptions = sorted(
        [exception for session in sessions for exception in session.exceptions
         if exception.original_date >= today or (exception.type == "moved" and exception.new_date >= today)],
        key=lambda row: (
            row.original_date,
            row.new_date or row.original_date,
            row.new_start_time or "",
            row.id,
        ),
    )
    snap = occ_src.load_snapshot(db)
    session_rows = []
    for row in sessions:
        ns = snap.sessions.get(row.id)
        row_data = SessionWithRoomRead.model_validate(row).model_dump()
        if ns is not None:
            row_data["repeat"] = occ_src.session_repeat(ns)
            row_data["repeat_label"] = occ_src.repeat_label(ns)
            row_data["next_dates"] = occ_src.next_dates(snap, row.id, limit=3)
        session_rows.append(row_data)
    return {
        **ClubRead.model_validate(item).model_dump(),
        "category": item.category,
        "leader": item.leader,
        "leaders": item.leaders or [item.leader],
        "sessions": session_rows,
        "upcoming_exceptions": upcoming_exceptions,
        "upcoming_events": upcoming_events[:8],
    }


@router.get("/schedule", response_model=list[ScheduleEvent])
def schedule(
    week: str,
    category_id: int | None = Query(None, gt=0),
    weekday: int | None = Query(None, ge=1, le=6),
    leader_id: int | None = Query(None, gt=0),
    room_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    week_start = _parse_week_start(week)
    events = occ_src.week_events(occ_src.load_snapshot(db), week_start)
    return _filter_events(events, category_id, weekday, leader_id, room_id, search)


def _filter_events(events, category_id, weekday, leader_id, room_id, search):
    if category_id is not None:
        events = [event for event in events if event["category_id"] == category_id]
    if weekday is not None:
        events = [
            event
            for event in events
            if date.fromisoformat(event["date"]).isoweekday() == weekday
        ]
    if leader_id is not None:
        events = [event for event in events if leader_id in (event.get("leader_ids") or [event["leader_id"]])]
    if room_id is not None:
        events = [event for event in events if room_id in (event.get("room_ids") or [event["room_id"]])]
    if search:
        needle = search.strip().casefold()
        events = [
            event
            for event in events
            if needle in event["club_name"].casefold()
            or needle in event["category_name"].casefold()
            or needle in event["leader_name"].casefold()
            or needle in event["room_name"].casefold()
            or any(needle in name.casefold() for name in event.get("leader_names", []))
            or any(needle in name.casefold() for name in event.get("room_names", []))
        ]
    return events

@router.get("/clubs/{club_id}/calendar.ics")
def export_club_calendar(
    club_id: Annotated[int, Path(gt=0)],
    week: Annotated[
        str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    ] = None,
    start: str | None = None,
    end: str | None = None,
    date_from: Annotated[str | None, Query(alias="from", pattern=_DATE_PATTERN)] = None,
    date_to: Annotated[str | None, Query(alias="to", pattern=_DATE_PATTERN)] = None,
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(Club).where(Club.id == club_id, Club.is_active.is_(True))
    )
    if week and (start or end or date_from or date_to):
        raise HTTPException(422, "Выберите неделю или диапазон дат")
    if week is not None:
        week_start = _parse_week_start(week)
        if week_start > date.max - timedelta(days=6):
            raise HTTPException(422, "Неделя выходит за диапазон дат")
        if item is None:
            raise HTTPException(404, "Кружок не найден")
        calendar_text = build_club_calendar(
            week_start=week_start,
            db=db,
            club_id=item.id,
            club_name=item.name,
        )
        return _ics_response(calendar_text, f"club-{item.id}-{week_start.isoformat()}.ics")
    if item is None:
        raise HTTPException(404, "Кружок не найден")
    snap = occ_src.load_snapshot(db)
    if start or end:
        # диапазон из карточки кружка (T4): ?start=&end=, не длиннее 93 дней
        try:
            if not start or not end or not _WEEK_RE.fullmatch(start) or not _WEEK_RE.fullmatch(end):
                raise ValueError
            range_start, range_end = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise HTTPException(422, "Укажите корректные даты начала и конца") from exc
        if range_start < MIN_WEEK or range_end > MAX_WEEK + timedelta(days=6) or range_end < range_start or (range_end - range_start).days > 92:
            raise HTTPException(422, "Диапазон должен быть не более 93 дней и в пределах поддерживаемого календаря")
    else:
        range_start, range_end = _window(snap, date_from, date_to)
    text_ics = build_calendar(snap, range_start, range_end, club_ids=[item.id], title=item.name)
    return _ics_response(text_ics, f"club-{item.id}-{range_start.isoformat()}.ics")


@router.get("/sessions/{session_id}/calendar.ics")
def export_session_calendar(
    session_id: Annotated[int, Path(gt=0)],
    date_from: Annotated[str | None, Query(alias="from", pattern=_DATE_PATTERN)] = None,
    date_to: Annotated[str | None, Query(alias="to", pattern=_DATE_PATTERN)] = None,
    db: Session = Depends(get_db),
):
    snap = occ_src.load_snapshot(db)
    session = _public_session_or_404(snap, session_id)
    club = snap.clubs[session.club_id]
    start, end = _window(snap, date_from, date_to)
    text_ics = build_calendar(snap, start, end, session_ids=[session_id], title=club.name)
    return _ics_response(text_ics, f"session-{session_id}.ics")


@router.get("/calendar.ics")
def export_full_calendar(
    date_from: Annotated[str | None, Query(alias="from", pattern=_DATE_PATTERN)] = None,
    date_to: Annotated[str | None, Query(alias="to", pattern=_DATE_PATTERN)] = None,
    club_id: Annotated[list[int] | None, Query()] = None,
    db: Session = Depends(get_db),
):
    snap = occ_src.load_snapshot(db)
    start, end = _window(snap, date_from, date_to)
    text_ics = build_calendar(snap, start, end, club_ids=club_id, title="Расписание кружков")
    return _ics_response(text_ics, "kipclub.ics")


@router.get("/sessions/{session_id}/occurrences")
def session_occurrences(
    session_id: Annotated[int, Path(gt=0)],
    date_from: Annotated[str | None, Query(alias="from", pattern=_DATE_PATTERN)] = None,
    date_to: Annotated[str | None, Query(alias="to", pattern=_DATE_PATTERN)] = None,
    db: Session = Depends(get_db),
):
    snap = occ_src.load_snapshot(db)
    session = _public_session_or_404(snap, session_id)
    start, end = _window(snap, date_from, date_to)
    items = occ_src.snapshot_occurrences(snap, start, end, session_ids=[session_id])
    return {
        "session_id": session_id,
        "club_id": session.club_id,
        "repeat": occ_src.session_repeat(session),
        "repeat_label": occ_src.repeat_label(session),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "items": [occ_src.occurrence_dict(o) for o in items],
    }


@router.get("/clubs/{club_id}/occurrences")
def club_occurrences(
    club_id: Annotated[int, Path(gt=0)],
    date_from: Annotated[str | None, Query(alias="from", pattern=_DATE_PATTERN)] = None,
    date_to: Annotated[str | None, Query(alias="to", pattern=_DATE_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    db: Session = Depends(get_db),
):
    snap = occ_src.load_snapshot(db)
    club = snap.clubs.get(club_id)
    if club is None or not club.is_active:
        raise HTTPException(404, "Кружок не найден")
    start, end = _window(snap, date_from, date_to)
    sids = [s.id for s in snap.sessions.values() if s.club_id == club_id]
    items = occ_src.snapshot_occurrences(snap, start, end, session_ids=sids)
    upcoming = [o.date.isoformat() for o in items if o.occupies]
    return {
        "club_id": club_id,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "next_dates": sorted(set(upcoming))[:5],
        "items": [occ_src.occurrence_dict(o) for o in items][:limit],
    }


@router.get("/week")
def week_payload(
    week: str,
    category_id: int | None = Query(None, gt=0),
    weekday: int | None = Query(None, ge=1, le=6),
    leader_id: int | None = Query(None, gt=0),
    room_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    week_start = _parse_week_start(week)
    week_end = week_start + timedelta(days=6)
    snap = occ_src.load_snapshot(db)
    events = _filter_events(occ_src.week_events(snap, week_start), category_id, weekday, leader_id, room_id, search)
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "parity": _safe_parity(snap, week_start),
        "period": occ_src.period_info(snap, week_start) or occ_src.period_info(snap, week_end),
        "no_class": occ_src.no_class_in(snap, week_start, week_end),
        "events": [ScheduleEvent.model_validate(e).model_dump(mode="json") for e in events],
    }


_MAX_WINDOW_DAYS = 400


def _window(snap, date_from: str | None, date_to: str | None) -> tuple[date, date]:
    start, end = occ_src.default_window(snap)
    try:
        if date_from:
            start = date.fromisoformat(date_from)
        if date_to:
            end = date.fromisoformat(date_to)
    except ValueError as exc:
        raise HTTPException(422, "Неверная дата") from exc
    if end < start:
        raise HTTPException(422, "Конец периода раньше начала")
    if (end - start).days > _MAX_WINDOW_DAYS:
        raise HTTPException(422, f"Период не длиннее {_MAX_WINDOW_DAYS} дней")
    return start, end


def _public_session_or_404(snap, session_id: int):
    session = snap.sessions.get(session_id)
    club = snap.clubs.get(session.club_id) if session is not None else None
    if session is None or club is None or not club.is_active:
        raise HTTPException(404, "Занятие не найдено")
    return session


def _safe_parity(snap, day: date):
    fn = getattr(snap.calendar, "parity", None)
    try:
        return fn(day) if fn else None
    except Exception:  # noqa: BLE001
        return None


def _ics_response(calendar_text: str, filename: str) -> Response:
    return Response(
        content=calendar_text.encode("utf-8"),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
