"""Админ-API schedule v2: отчёт о конфликтах, разрешения «совместное занятие», публикация импорта."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.admin import Admin
from ..services import audit, import_publish
from ..services import conflicts as engine
from .admin import _confirmed_conflicts, require_admin, schedule_write_lock

router = APIRouter(prefix="/api/admin", tags=["admin-schedule"])


def _date(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, f"{name}: ожидается YYYY-MM-DD") from exc


@router.get("/conflicts", dependencies=[Depends(require_admin)])
def list_conflicts(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    include_allowed: bool = False,
    db: Session = Depends(get_db),
):
    start, end = _date(date_from, "from"), _date(date_to, "to")
    if start and end and (end < start or (end - start).days > 400):
        raise HTTPException(422, "Окно: конец не раньше начала и не длиннее 400 дней")
    data = engine.report(db, start, end)
    if not include_allowed:
        data["items"] = [i for i in data["items"] if not i["allowed"]]
    return data


class OverrideCreate(BaseModel):
    session_a: int = Field(gt=0)
    session_b: int = Field(gt=0)
    date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    comment: str = Field("", max_length=500)


@router.get("/conflicts/overrides", dependencies=[Depends(require_admin)])
def list_overrides():
    return {"items": engine.ConflictOverrides().load()}


@router.post("/conflicts/overrides", status_code=201, dependencies=[Depends(schedule_write_lock)])
def add_override(payload: OverrideCreate, db: Session = Depends(get_db), admin: Admin = Depends(require_admin)):
    if payload.session_a == payload.session_b:
        raise HTTPException(422, "Нужны два разных занятия")
    from ..models.session import ClubSession

    for sid in (payload.session_a, payload.session_b):
        if db.get(ClubSession, sid) is None:
            raise HTTPException(404, f"Занятие {sid} не найдено")
    item = engine.ConflictOverrides().add(payload.session_a, payload.session_b, on_date=payload.date, comment=payload.comment)
    audit.log("conflict_override_added", admin_id=admin.id, override=item)
    return item


@router.delete("/conflicts/overrides/{override_id}", status_code=204, dependencies=[Depends(schedule_write_lock)])
def delete_override(override_id: int, admin: Admin = Depends(require_admin)):
    if not engine.ConflictOverrides().remove(override_id):
        raise HTTPException(404, "Разрешение не найдено")
    audit.log("conflict_override_removed", admin_id=admin.id, override_id=override_id)


@router.post("/import/publish", dependencies=[Depends(schedule_write_lock)])
def publish_import(
    dataset: dict[str, Any] = Body(...),
    dry_run: bool = False,
    prune: bool = True,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
):
    try:
        result = import_publish.publish(db, dataset, dry_run=dry_run, prune=prune, author=admin.login, confirmed=_confirmed_conflicts.get())
    except import_publish.ImportError_ as exc:
        status = 409 if exc.conflicts else 422
        raise HTTPException(status, {"code": "IMPORT_REJECTED", "message": str(exc), "errors": exc.errors, "conflicts": exc.conflicts, "confirmation_token": exc.confirmation_token}) from exc
    if not dry_run:
        audit.log("import_published", admin_id=admin.id, publish=result.get("publish"))
    return result


@router.get("/import/publishes", dependencies=[Depends(require_admin)])
def publish_history():
    return {"items": list(reversed(import_publish.history()))}


@router.post("/import/publishes/{publish_id}/rollback", dependencies=[Depends(schedule_write_lock)])
def rollback_publish(publish_id: int, admin: Admin = Depends(require_admin)):
    try:
        result = import_publish.rollback(publish_id)
    except import_publish.ImportError_ as exc:
        raise HTTPException(404, str(exc)) from exc
    audit.log("import_rolled_back", admin_id=admin.id, publish_id=publish_id)
    return result
