"""Рассылки администратора («Рассылки» в админке) и публичная лента объявлений для приложения (APK без FCM).

Админ: GET /api/admin/broadcasts (журнал), POST /api/admin/broadcasts/estimate (охват), POST /api/admin/broadcasts (отправить).
Публично: GET /api/announcements?since=<id>&clubs=1,2[&device=<id установки>&off=1] — объявления «всем» и для указанных кружков.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.broadcast import Broadcast
from ..models.broadcast_schedule import BroadcastSchedule
from ..models.club import Club
from ..models.session import ClubSession
from ..schemas.broadcast import AudienceIn, BroadcastCreate
from ..services import audit, broadcast_receipts, scheduled_broadcasts
from ..services import broadcast as service
from .admin import require_admin

router = APIRouter(tags=["announcements"])
DEDUPE_SECONDS = 120     # то же объявление тем же админом — не чаще
FEED_DAYS = 14           # лента для приложения: последние две недели
FEED_LIMIT = 20


def _check_audience(db: Session, a: AudienceIn) -> list[str]:
    """Проверяет кружки/занятия; возвращает названия кружков для журнала."""
    if a.audience == "all":
        return []
    clubs = {c.id: c.name for c in db.scalars(select(Club).where(Club.id.in_(a.club_ids)))}
    missing = [i for i in a.club_ids if i not in clubs]
    if missing:
        raise HTTPException(422, "Кружок не найден: " + ", ".join(map(str, missing)))
    if a.session_ids:
        owners = dict(db.execute(select(ClubSession.id, ClubSession.club_id).where(ClubSession.id.in_(a.session_ids))).all())
        bad = [s for s in a.session_ids if owners.get(s) not in clubs]
        if bad:
            raise HTTPException(422, "Занятие не относится к выбранным кружкам: " + ", ".join(map(str, bad)))
        from ..services import occurrence_source

        idle = occurrence_source.sessions_without_upcoming(occurrence_source.load_snapshot(db), a.session_ids)
        if idle:
            raise HTTPException(422, "У занятия нет ближайших дат: " + ", ".join(map(str, idle)))
    return [clubs[i] for i in a.club_ids]


def _read(b: Broadcast, names: dict[int, str]) -> dict:
    club_ids = service.ids(b.club_ids)
    return {
        "id": b.id, "title": b.title, "body": b.body, "url": b.url, "audience": b.audience,
        "club_ids": club_ids, "club_names": [names.get(i, f"#{i}") for i in club_ids], "session_ids": service.ids(b.session_ids),
        "author": b.author_login, "created_at": b.created_at.isoformat(timespec="seconds") + "Z",
        "web_sent": b.web_sent, "web_failed": b.web_failed, "apk_targets": b.apk_targets,
        "fcm_sent": b.fcm_sent or 0, "fcm_failed": b.fcm_failed or 0,
    }


def _names(db: Session) -> dict[int, str]:
    return dict(db.execute(select(Club.id, Club.name)).all())


@router.get("/api/admin/broadcasts")
def history(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), _admin=Depends(require_admin)):
    rows = list(db.scalars(select(Broadcast).order_by(Broadcast.id.desc()).limit(limit)))
    names = _names(db)
    metrics = broadcast_receipts.counts(db, [b.id for b in rows])
    scheduled = list(db.scalars(select(BroadcastSchedule).where(BroadcastSchedule.status != "sent").order_by(BroadcastSchedule.created_at.desc()).limit(limit)))
    pending_ids = {s.broadcast_id for s in scheduled if s.broadcast_id}
    items = [{**_read(b, names), "status": "uncertain" if min(b.web_sent, b.web_failed, b.fcm_sent, b.fcm_failed) < 0 else "sent",
              "error": "Не подтверждён результат отправки", **metrics.get(b.id, {"shown": 0, "opened": 0})} for b in rows if b.id not in pending_ids]
    items += [scheduled_broadcasts.read(b) for b in scheduled]
    return {"items": sorted(items, key=lambda x: x["created_at"], reverse=True)[:limit]}


@router.post("/api/admin/broadcasts/estimate")
def estimate(payload: AudienceIn, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    _check_audience(db, payload)
    return service.estimate(db, payload.audience, payload.club_ids)


@router.post("/api/admin/broadcasts", status_code=201)
def send(payload: BroadcastCreate, request: Request, response: Response, db: Session = Depends(get_db), admin=Depends(require_admin)):
    planned = db.scalar(select(BroadcastSchedule).where(BroadcastSchedule.idempotency_key == payload.idempotency_key))
    if planned is not None:
        response.status_code = 200
        return {**scheduled_broadcasts.read(planned), "duplicate": True}
    existing = db.scalar(select(Broadcast).where(Broadcast.idempotency_key == payload.idempotency_key))
    if existing is not None:  # повтор того же запроса (двойное нажатие, ретрай сети) — ничего не шлём заново
        response.status_code = 200
        return {**_read(existing, _names(db)), "duplicate": True}
    names = _check_audience(db, payload)
    if payload.scheduled_at is not None:
        try:
            planned = scheduled_broadcasts.create(db, payload, admin)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit.log("broadcast_scheduled", admin_id=admin.id, schedule_id=planned.id)
        return {**scheduled_broadcasts.read(planned), "duplicate": False}
    recent = db.scalar(
        select(Broadcast).where(
            Broadcast.author_id == admin.id, Broadcast.title == payload.title, Broadcast.body == payload.body,
            Broadcast.audience == payload.audience, Broadcast.club_ids == json.dumps(payload.club_ids),
            Broadcast.created_at >= service._utcnow() - timedelta(seconds=DEDUPE_SECONDS),
        )
    )
    if recent is not None:
        raise HTTPException(409, "Такое объявление уже отправлено только что. Повторить можно через пару минут.")
    b = Broadcast(
        title=payload.title, body=payload.body, url=payload.url, audience=payload.audience,
        club_ids=json.dumps(payload.club_ids), session_ids=json.dumps(payload.session_ids),
        author_id=admin.id, author_login=admin.login, idempotency_key=payload.idempotency_key,
    )
    db.add(b)
    db.commit()
    service.dispatch(db, b)
    audit.log("broadcast_sent", admin_id=admin.id, broadcast_id=b.id, audience=b.audience, clubs=names,
              web_sent=b.web_sent, web_failed=b.web_failed, apk_targets=b.apk_targets, fcm_sent=b.fcm_sent,
              request_id=getattr(request.state, "request_id", None))
    return {**_read(b, _names(db)), "duplicate": False}


def _club_list(raw: str) -> list[int]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            if not part.isdigit() or len(out) >= 500:
                raise HTTPException(422, "clubs: список id через запятую")
            out.append(int(part))
    return out


@router.get("/api/announcements")
def feed(
    since: int = Query(0, ge=0),
    clubs: str = Query("", max_length=4000),
    device: str = Query("", max_length=64, pattern=r"^[A-Za-z0-9_-]*$"),
    off: int = Query(0, ge=0, le=1),
    db: Session = Depends(get_db),
):
    """Объявления для приложения: «всем» и для clubs. since — последний показанный id (0 — первый запуск)."""
    club_set = set(_club_list(clubs))
    if len(device) >= 16:
        service.touch_device(db, device, sorted(club_set), announcements=not off)
    last_id = db.scalar(select(func.max(Broadcast.id))) or 0
    items = []
    if not off:
        stmt = (select(Broadcast).where(Broadcast.id > since, Broadcast.created_at >= service._utcnow() - timedelta(days=FEED_DAYS))
                .order_by(Broadcast.id.desc()).limit(200))
        for b in db.scalars(stmt):
            if service.matches(b.audience, service.ids(b.club_ids), club_set):
                items.append({"id": b.id, "title": b.title, "body": b.body, "url": service.payload(b)["url"],
                              "created_at": b.created_at.isoformat(timespec="seconds") + "Z"})
            if len(items) >= FEED_LIMIT:
                break
    items.reverse()
    return Response(json.dumps({"items": items, "last_id": last_id}, ensure_ascii=False), media_type="application/json",
                    headers={"Cache-Control": "no-cache"})


@router.delete("/api/admin/broadcasts/schedules/{schedule_id}")
def cancel_scheduled(schedule_id: str, db: Session = Depends(get_db), admin=Depends(require_admin)):
    from sqlalchemy import update
    affected = db.execute(update(BroadcastSchedule).where(BroadcastSchedule.id == schedule_id, BroadcastSchedule.status == "scheduled")
                          .values(status="cancelled", updated_at=service._utcnow())).rowcount
    db.commit()
    if not affected:
        raise HTTPException(409, "Рассылка уже отправляется, отменена или не найдена")
    audit.log("broadcast_schedule_cancelled", admin_id=admin.id, schedule_id=schedule_id)
    return {"cancelled": True}


class Receipt(BaseModel):
    install_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    channel: Literal["web", "android"]
    kind: Literal["shown", "opened"]


@router.post("/api/announcements/{broadcast_id}/receipt", status_code=204)
def receipt(broadcast_id: int, payload: Receipt, db: Session = Depends(get_db)):
    if not 0 < broadcast_id < 2**53 or db.get(Broadcast, broadcast_id) is None:
        raise HTTPException(404, "Объявление не найдено")
    broadcast_receipts.mark(db, broadcast_id, payload.install_id, payload.channel, payload.kind)
    return Response(status_code=204)
