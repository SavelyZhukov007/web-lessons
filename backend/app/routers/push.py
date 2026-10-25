"""Публичные эндпоинты Web Push (без авторизации, как и остальной публичный API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.club import Club
from ..models.push_subscription import PushSubscription
from ..schemas.push import PushPreferencesRequest, PushStatusRequest, PushSubscribeRequest, PushUnsubscribeRequest
from ..services import push as push_service

router = APIRouter(prefix="/api/push", tags=["push"])

MAX_SUBSCRIPTIONS_PER_ENDPOINT = 60


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
    if payload.club_id is not None:
        club = db.scalar(select(Club).where(Club.id == payload.club_id, Club.is_active.is_(True)))
        if club is None:
            raise HTTPException(404, "Кружок не найден")

    same = select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    same = same.where(
        PushSubscription.club_id.is_(None)
        if payload.club_id is None
        else PushSubscription.club_id == payload.club_id
    )
    existing = db.scalar(same)
    if existing is not None:  # идемпотентность: обновляем ключи, ничего не дублируем
        existing.p256dh, existing.auth = payload.keys.p256dh, payload.keys.auth
        db.commit()
        response.status_code = 200
        return {"status": "already-subscribed", "club_id": payload.club_id}

    total = db.scalar(
        select(func.count()).select_from(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if total >= MAX_SUBSCRIPTIONS_PER_ENDPOINT:
        raise HTTPException(429, "Слишком много подписок для этого устройства")
    # выбор «Объявления» относится к браузеру целиком: новая подписка наследует его
    opted_out = db.scalar(
        select(func.count()).select_from(PushSubscription)
        .where(PushSubscription.endpoint == payload.endpoint, PushSubscription.announcements.is_(False))
    )
    db.add(
        PushSubscription(
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            club_id=payload.club_id,
            announcements=not opted_out,
        )
    )
    # те же ключи на других подписках этого endpoint могли устареть
    db.execute(
        PushSubscription.__table__.update()
        .where(PushSubscription.endpoint == payload.endpoint)
        .values(p256dh=payload.keys.p256dh, auth=payload.keys.auth)
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
    """На какие кружки подписан этот endpoint (чтобы кнопка на странице показывала правильное состояние)."""
    rows = list(db.execute(select(PushSubscription.club_id, PushSubscription.announcements).where(PushSubscription.endpoint == payload.endpoint)))
    return {"all": any(r[0] is None for r in rows), "club_ids": sorted(r[0] for r in rows if r[0] is not None),
            "announcements": all(r[1] for r in rows) if rows else True}


@router.post("/preferences")
def preferences(payload: PushPreferencesRequest, db: Session = Depends(get_db)):
    """«Объявления» вкл/выкл для всех подписок этого браузера (переносы и отмены не затрагивает)."""
    updated = db.execute(
        PushSubscription.__table__.update().where(PushSubscription.endpoint == payload.endpoint).values(announcements=payload.announcements)
    ).rowcount
    db.commit()
    return {"updated": updated, "announcements": payload.announcements}
