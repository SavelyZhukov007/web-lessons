"""Рассылки администратора («Рассылки» в админке) и публичная лента объявлений для приложения (APK без FCM).

Админ: GET /api/admin/broadcasts (журнал), POST /api/admin/broadcasts/estimate (охват), POST /api/admin/broadcasts (отправить).
Публично: GET /api/announcements?since=<id>&clubs=1,2[&device=<id установки>&off=1] — объявления «всем» и для указанных кружков.
"""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.broadcast import Broadcast
from ..models.club import Club
from ..models.session import ClubSession
from ..schemas.broadcast import AudienceIn, BroadcastCreate
from ..services import audit
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
    rows = db.scalars(select(Broadcast).order_by(Broadcast.id.desc()).limit(limit))
    names = _names(db)
    return {"items": [_read(b, names) for b in rows]}


@router.post("/api/admin/broadcasts/estimate")
def estimate(payload: AudienceIn, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    _check_audience(db, payload)
    return service.estimate(db, payload.audience, payload.club_ids)


@router.post("/api/admin/broadcasts", status_code=201)
def send(payload: BroadcastCreate, request: Request, response: Response, db: Session = Depends(get_db), admin=Depends(require_admin)):
    existing = db.scalar(select(Broadcast).where(Broadcast.idempotency_key == payload.idempotency_key))
    if existing is not None:  # повтор того же запроса (двойное нажатие, ретрай сети) — ничего не шлём заново
        response.status_code = 200
        return {**_read(existing, _names(db)), "duplicate": True}
    names = _check_audience(db, payload)
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
                items.append({"id": b.id, "title": b.title, "body": b.body, "url": b.url or "/",
                              "created_at": b.created_at.isoformat(timespec="seconds") + "Z"})
            if len(items) >= FEED_LIMIT:
                break
    items.reverse()
    return Response(json.dumps({"items": items, "last_id": last_id}, ensure_ascii=False), media_type="application/json",
                    headers={"Cache-Control": "no-cache"})
