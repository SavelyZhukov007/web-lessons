"""Публичные эндпоинты Web Push (без авторизации, как и остальной публичный API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.club import Club
from ..models.push_subscription import PushSubscription
from ..schemas.push import PushPreferencesRequest, PushStatusRequest, PushSubscribeRequest, PushSyncRequest, PushUnsubscribeRequest
from ..services import push as push_service

router = APIRouter(prefix="/api/push", tags=["push"])

MAX_SUBSCRIPTIONS_PER_ENDPOINT = 60
PREFERENCE_FIELDS = ("announcements", "cancellations", "moves")


def _rows(db: Session, endpoint: str) -> list[PushSubscription]:
    return list(db.scalars(select(PushSubscription).where(PushSubscription.endpoint == endpoint)))


def _status(rows: list[PushSubscription]) -> dict:
    return {
        "all": any(row.club_id is None and not row.announcements_only for row in rows),
        "general": any(row.announcements_only for row in rows),
        "club_ids": sorted({row.club_id for row in rows if row.club_id is not None}),
        **{field: all(getattr(row, field) for row in rows) for field in PREFERENCE_FIELDS},
    }


@router.get("/vapid-public-key")
def vapid_public_key():
    try:
        return {"publicKey": push_service.get_vapid_keys().public_key}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "Push-уведомления на сервере не настроены") from exc


@router.post("/subscribe")
def subscribe(payload: PushSubscribeRequest, response: Response, db: Session = Depends(get_db)):
    if not push_service.endpoint_allowed(payload.endpoint):
        raise HTTPException(422, "Неподдерживаемый push-сервис (endpoint не из списка разрешённых)")
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    if payload.club_id is not None:
        club = db.scalar(select(Club).where(Club.id == payload.club_id, Club.is_active.is_(True)))
        if club is None:
            raise HTTPException(404, "Кружок не найден")

    rows = _rows(db, payload.endpoint)
    existing = next((row for row in rows if not row.announcements_only and row.club_id == payload.club_id), None)
    for row in rows:
        row.p256dh, row.auth = payload.keys.p256dh, payload.keys.auth
    if existing is not None:  # идемпотентность: обновляем ключи, ничего не дублируем
        db.commit()
        response.status_code = 200
        return {"status": "already-subscribed", "club_id": payload.club_id}

    if sum(not row.announcements_only for row in rows) >= MAX_SUBSCRIPTIONS_PER_ENDPOINT:
        raise HTTPException(429, "Слишком много подписок для этого устройства")
    prefs = _status(rows)
    db.add(
        PushSubscription(
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            club_id=payload.club_id,
            **{field: prefs[field] for field in PREFERENCE_FIELDS},
        )
    )
    db.commit()
    response.status_code = 201
    return {"status": "subscribed", "club_id": payload.club_id}


@router.post("/unsubscribe")
def unsubscribe(payload: PushUnsubscribeRequest, db: Session = Depends(get_db)):
    stmt = delete(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    if payload.club_id is not None:
        stmt = stmt.where(PushSubscription.club_id == payload.club_id)
    removed = db.execute(stmt).rowcount
    db.commit()
    remaining = db.scalar(
        select(func.count()).select_from(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    return {"removed": removed, "remaining": remaining}


@router.post("/status")
def status(payload: PushStatusRequest, db: Session = Depends(get_db)):
    return _status(_rows(db, payload.endpoint))


@router.post("/preferences")
def preferences(payload: PushPreferencesRequest, db: Session = Depends(get_db)):
    values = payload.model_dump(exclude={"endpoint"}, exclude_none=True)
    updated = db.execute(
        PushSubscription.__table__.update().where(PushSubscription.endpoint == payload.endpoint).values(**values)
    ).rowcount
    db.commit()
    return {"updated": updated, **values}


@router.post("/sync")
def sync(payload: PushSyncRequest, db: Session = Depends(get_db)):
    """Атомарно сохранить список кружков и согласие на общие объявления этой установки."""
    if not push_service.endpoint_allowed(payload.endpoint):
        raise HTTPException(422, "Неподдерживаемый push-сервис (endpoint не из списка разрешённых)")
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    active = db.scalars(select(Club.id).where(Club.id.in_(payload.club_ids), Club.is_active.is_(True)))
    wanted = {(club_id, False) for club_id in active} | {(None, True)}
    kept = {}
    for row in _rows(db, payload.endpoint):
        scope = (row.club_id, row.announcements_only)
        if scope in wanted and scope not in kept:
            kept[scope] = row
        else:
            db.delete(row)
    for club_id, general in wanted:
        row = kept.get((club_id, general))
        if row is None:
            row = PushSubscription(endpoint=payload.endpoint, club_id=club_id, announcements_only=general)
            db.add(row)
            kept[club_id, general] = row
        row.p256dh, row.auth = payload.keys.p256dh, payload.keys.auth
        for field in PREFERENCE_FIELDS:
            setattr(row, field, getattr(payload, field))
    db.commit()
    return _status(list(kept.values()))
