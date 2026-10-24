from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models.category import Category
from ..models.club import Club
from ..models.leader import Leader
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
from ..services.calendar_export import build_club_calendar
from ..services.schedule import build_week

router = APIRouter(prefix="/api", tags=["public"])


MIN_WEEK = date(2000, 1, 3)
MAX_WEEK = date(2100, 12, 27)
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


@router.get("/categories", response_model=list[CategoryRead])
def categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name, Category.id)))


@router.get("/leaders", response_model=list[LeaderPublic])
def leaders(db: Session = Depends(get_db)):
    """Только руководители активных кружков и без контактов (SEC-07)."""
    active = select(Club.leader_id).where(Club.is_active.is_(True))
    return list(
        db.scalars(select(Leader).where(Leader.id.in_(active)).order_by(Leader.name, Leader.id))
    )


@router.get("/rooms", response_model=list[RoomRead])
def rooms(db: Session = Depends(get_db)):
    return list(db.scalars(select(Room).order_by(Room.building, Room.name, Room.id)))


@router.get("/clubs", response_model=list[ClubRead])
def clubs(
    search: str | None = None,
    category_id: int | None = None,
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
    upcoming_exceptions = sorted(
        [exception for session in sessions for exception in session.exceptions],
        key=lambda row: (
            row.original_date,
            row.new_date or row.original_date,
            row.new_start_time or "",
            row.id,
        ),
    )
    return {
        **ClubRead.model_validate(item).model_dump(),
        "category": item.category,
        "leader": item.leader,
        "sessions": sessions,
        "upcoming_exceptions": upcoming_exceptions,
    }


@router.get("/schedule", response_model=list[ScheduleEvent])
def schedule(
    week: str,
    category_id: int | None = None,
    weekday: int | None = None,
    leader_id: int | None = None,
    room_id: int | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    week_start = _parse_week_start(week)
    events = build_week(week_start, _dump_schedule_data(db))

    if category_id is not None:
        events = [event for event in events if event["category_id"] == category_id]
    if weekday is not None:
        events = [
            event
            for event in events
            if date.fromisoformat(event["date"]).isoweekday() == weekday
        ]
    if leader_id is not None:
        events = [event for event in events if event["leader_id"] == leader_id]
    if room_id is not None:
        events = [event for event in events if event["room_id"] == room_id]
    if search:
        needle = search.strip().casefold()
        events = [
            event
            for event in events
            if needle in event["club_name"].casefold()
            or needle in event["category_name"].casefold()
            or needle in event["leader_name"].casefold()
            or needle in event["room_name"].casefold()
        ]
    return events

@router.get("/clubs/{club_id}/calendar.ics")
def export_club_calendar(
    club_id: Annotated[int, Path(gt=0)],
    week: Annotated[
        str, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    ],
    db: Session = Depends(get_db),
):
    week_start = _parse_week_start(week)
    if week_start > date.max - timedelta(days=6):
        raise HTTPException(422, "Неделя выходит за диапазон дат")
    item = db.scalar(
        select(Club).where(Club.id == club_id, Club.is_active.is_(True))
    )
    if item is None:
        raise HTTPException(404, "Кружок не найден")
    calendar_text = build_club_calendar(
        week_start=week_start,
        data=_dump_schedule_data(db),
        club_id=item.id,
        club_name=item.name,
    )
    filename = f"club-{item.id}-{week_start.isoformat()}.ics"
    return Response(
        content=calendar_text.encode("utf-8"),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
