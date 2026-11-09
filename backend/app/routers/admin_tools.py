"""Admin action ledger and atomic, previewable bulk schedule operations."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ClubSession, SessionException
from ..schemas.session_exception import MoveCreate
from ..services import import_journal, occurrence_source
from ..services.push import notify_exception
from .admin import require_admin, schedule_write_lock

router = APIRouter(prefix="/api/admin", tags=["admin-tools"])


@router.get("/actions", dependencies=[Depends(require_admin)])
def actions(limit: int = Query(100, ge=1, le=500), request_id: str = Query("", max_length=100), db: Session = Depends(get_db)):
    items = list(reversed(import_journal.history(db, include_actions=True)))
    if request_id:
        items = [x for x in items if x.get("request_id") == request_id]
    return {"items": items[:limit]}


@router.post("/actions/{action_id}/undo", dependencies=[Depends(schedule_write_lock)])
def undo(action_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    try:
        return import_journal.rollback(db, action_id, author=admin.login)
    except import_journal.RollbackError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


class Bulk(BaseModel):
    action: Literal["cancel", "delete"]
    session_ids: list[PositiveInt] = Field(min_length=1, max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    comment: str = Field("", max_length=500)
    preview: bool = True
    confirmation: str = Field("", max_length=64)
    notify: bool = False


@router.post("/bulk", dependencies=[Depends(schedule_write_lock)])
def bulk(payload: Bulk, background: BackgroundTasks, db: Session = Depends(get_db)):
    ids = sorted(set(payload.session_ids))
    rows = list(db.scalars(select(ClubSession).where(ClubSession.id.in_(ids))))
    if len(rows) != len(ids):
        raise HTTPException(409, "Часть занятий уже удалена. Обновите список.")
    before = import_journal.capture(db)
    items = []
    if payload.action == "cancel":
        if not payload.date_from or not payload.date_to or not 0 <= (payload.date_to - payload.date_from).days <= 31:
            raise HTTPException(422, "Укажите диапазон отмен до 32 дней включительно")
        snapshot = occurrence_source.load_snapshot(db)
        for occurrence in occurrence_source.snapshot_occurrences(snapshot, payload.date_from, payload.date_to):
            if occurrence.occupies and occurrence.source_session_id in ids:
                club = snapshot.clubs.get(occurrence.club_id)
                items.append(
                    {
                        "session_id": occurrence.source_session_id,
                        "date": occurrence.date.isoformat(),
                        "original_date": (occurrence.original_date or occurrence.date).isoformat(),
                        "exception_id": occurrence.exception_id,
                        "title": getattr(club, "name", "Занятие"),
                    }
                )
    else:
        items = [{"session_id": s.id, "title": s.club.name, "exceptions": len(s.exceptions)} for s in rows]
    # Revalidate the entire relevant snapshot at confirmation: no stale bulk preview can silently change scope.
    token = hashlib.sha256(
        json.dumps(
            {"before": before, "payload": payload.model_dump(mode="json", exclude={"preview", "confirmation"}), "items": items},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    result = {"items": items, "count": len(items), "confirmation": token, "preview": payload.preview}
    if payload.preview:
        return result
    if payload.confirmation != token:
        raise HTTPException(409, "Расписание изменилось. Сначала повторите предварительный просмотр.")
    notified = []
    if payload.action == "delete":
        for row in rows:
            db.delete(row)
    else:
        for item in items:
            row = db.get(SessionException, item["exception_id"]) if item["exception_id"] else None
            if row is None:
                row = SessionException(session_id=item["session_id"], original_date=item["original_date"])
                db.add(row)
            row.type = "cancelled"
            row.new_date = row.new_start_time = row.new_end_time = row.new_room_id = None
            row.comment = payload.comment
            notified.append(row)
    db.commit()  # The action journal is captured by the before_commit hook in the same transaction.
    if payload.notify:
        for row in notified:
            background.add_task(notify_exception, row.id)
    return result


@router.get("/export", dependencies=[Depends(require_admin)])
def export_schedule(
    date_from: date,
    date_to: date,
    format: Literal["json", "xlsx", "pdf"] = "json",
    building: str = Query("", max_length=200),
    room_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response

    from ..services import admin_export

    if not 0 <= (date_to - date_from).days <= 31:
        raise HTTPException(422, "Диапазон выгрузки — до 32 дней включительно")
    data = admin_export.rows(db, date_from, date_to, building=building, room_id=room_id)
    if len(data) > 5000:
        raise HTTPException(422, "Слишком много строк. Выберите меньший период или аудиторию.")
    if format == "json":
        return {"headers": admin_export.HEADERS, "rows": data}
    title = f"Расписание {date_from} — {date_to}" + (" · " + building if building else "")
    content = admin_export.xlsx(data) if format == "xlsx" else admin_export.pdf(data, title)
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "application/pdf"
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="kipclub-{date_from}.{format}"', "Cache-Control": "no-store"},
    )


def calendar_events(db, week):
    from ..models.import_publication import ScheduleRowRevision

    revisions = {(r.table_name, r.row_key): r.revision for r in db.scalars(select(ScheduleRowRevision))}
    snapshot = occurrence_source.load_snapshot(db)
    exceptions = {(e.session_id, str(e.original_date)[:10]): e.id for e in snapshot.exceptions}
    events = occurrence_source.week_events(snapshot, week)
    for item in events:
        item["exception_id"] = exceptions.get((item["session_id"], item.get("original_date") or item["date"]))
        fingerprint = {
            "event": item,
            "session_revision": revisions.get(("sessions", f"[{item['session_id']}]")),
            "exception_revision": revisions.get(("session_exceptions", f"[{item.get('exception_id')}]")),
        }
        item["revision"] = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return events


@router.get("/calendar", dependencies=[Depends(require_admin)])
def calendar(week: date, db: Session = Depends(get_db)):
    if week.isoweekday() != 1 or not 1900 <= week.year <= 9998:
        raise HTTPException(422, "Укажите понедельник недели")
    return {"items": calendar_events(db, week)}


class CalendarMove(BaseModel):
    source_date: date
    event_id: str = Field(max_length=100)
    revision: str = Field(min_length=64, max_length=64)
    move: MoveCreate


@router.post("/calendar/move", dependencies=[Depends(schedule_write_lock)])
def calendar_move(payload: CalendarMove, background: BackgroundTasks, db: Session = Depends(get_db)):
    from datetime import timedelta

    from ..schemas.session_exception import MoveUpdate
    from .admin import create_move, update_exception

    if not 1900 <= payload.source_date.year <= 9998:
        raise HTTPException(422, "Дата вне диапазона календаря")
    week = payload.source_date - timedelta(days=payload.source_date.weekday())
    item = next(
        (e for e in calendar_events(db, week) if e["event_id"] == payload.event_id and e["date"] == payload.source_date.isoformat()), None
    )
    if not item or item["revision"] != payload.revision or item["status"] == "cancelled":
        raise HTTPException(409, "Занятие изменилось. Обновите календарь перед переносом.")
    original = item.get("original_date") or item["date"]
    if item["session_id"] != payload.move.session_id or original != payload.move.original_date.isoformat():
        raise HTTPException(422, "Исходное занятие не совпадает")
    if item.get("exception_id"):
        data = payload.move.model_dump(exclude={"session_id", "original_date"})
        return update_exception(
            item["exception_id"], background, MoveUpdate.model_validate(data).model_dump(mode="json", exclude_unset=True), db
        )
    return create_move(payload.move, background, db)
