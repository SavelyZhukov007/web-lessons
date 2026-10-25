"""Рассылки администратора (объявления): аудитория, оценка охвата и доставка.

Каналы (services/delivery): Web Push на push_subscriptions с флагом announcements и FCM на зарегистрированные
установки APK; кроме того, APK опрашивает GET /api/announcements (SyncWorker ~30 мин и при открытии) — резервный путь,
поэтому apk_targets — число активных установок, которые увидят объявление в любом случае.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.broadcast import AppDevice, Broadcast
from . import delivery

log = logging.getLogger("clubs.broadcast")
DEVICE_ACTIVE_DAYS = 30   # установка «живая», если опрашивала сервер за это время
DEVICE_FORGET_DAYS = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ids(raw: str | None) -> list[int]:
    try:
        return [int(x) for x in json.loads(raw or "[]")]
    except (ValueError, TypeError):
        return []


def payload(b: Broadcast) -> dict:
    return {"title": b.title, "body": b.body, "url": b.url or "/", "tag": f"broadcast-{b.id}", "kind": "announcement",
            "broadcast_id": b.id}


def matches(audience: str, target: list[int], clubs: set[int] | None) -> bool:
    """clubs=None — подписчик «все кружки» (получает и адресные объявления)."""
    return audience == "all" or clubs is None or bool(set(target) & clubs)


def event(b: Broadcast) -> delivery.Event:
    return delivery.Event(kind="announcement", audience=b.audience, club_ids=ids(b.club_ids), payload=payload(b),
                          data={"id": b.id})


def _audience_event(audience: str, club_ids: list[int]) -> delivery.Event:
    return delivery.Event(kind="announcement", audience=audience, club_ids=club_ids, payload={"tag": "estimate"})


def _apk_targets(db: Session, audience: str, club_ids: list[int]) -> int:
    since = _utcnow() - timedelta(days=DEVICE_ACTIVE_DAYS)
    rows = db.scalars(select(AppDevice).where(AppDevice.last_seen >= since, AppDevice.announcements.is_(True)))
    return sum(1 for d in rows if matches(audience, club_ids, set(ids(d.club_ids))))


def estimate(db: Session, audience: str, club_ids: list[int]) -> dict:
    ev = _audience_event(audience, club_ids)
    return {"web": len(delivery.web_targets(db, ev)), "apk": _apk_targets(db, audience, club_ids),
            "fcm": delivery.estimate_fcm(db, ev)}


def dispatch(db: Session, b: Broadcast) -> Broadcast:
    """Доставка по всем каналам (delivery.deliver); итоги пишутся в строку рассылки. Не бросает исключений."""
    r = delivery.deliver(db, event(b))
    b.web_sent, b.web_failed, b.fcm_sent, b.fcm_failed = r.web_sent, r.web_failed, r.fcm_sent, r.fcm_failed
    b.apk_targets = _apk_targets(db, b.audience, ids(b.club_ids))  # без FCM APK заберёт объявление сам при опросе
    db.commit()
    return b


def device_key(device_id: str) -> str:
    import hashlib

    return hashlib.sha256(("app-device|" + device_id).encode()).hexdigest()


def _device_row(db: Session, device_id: str) -> AppDevice:
    key = device_key(device_id)
    row = db.get(AppDevice, key)
    if row is None:
        row = AppDevice(id_hash=key, club_ids="[]", announcements=True, notify_changes=True, platform="android", app_version="")
        db.add(row)
        db.execute(delete(AppDevice).where(AppDevice.last_seen < _utcnow() - timedelta(days=DEVICE_FORGET_DAYS)))
    return row


def touch_device(db: Session, device_id: str, clubs: list[int], announcements: bool = True) -> None:
    row = _device_row(db, device_id)
    row.club_ids, row.announcements, row.last_seen = json.dumps(sorted(set(clubs))), announcements, _utcnow()
    db.commit()


def register_device(db: Session, device_id: str, token: str | None, platform: str, app_version: str,
                    clubs: list[int], announcements: bool, changes: bool) -> None:
    """POST /api/app/devices: FCM-токен и настройки установки (та же строка, что и у опроса объявлений)."""
    row = _device_row(db, device_id)
    if token:  # токен принадлежит одной установке: если он переехал (переустановка) — снимаем со старой строки
        for other in db.scalars(select(AppDevice).where(AppDevice.fcm_token == token, AppDevice.id_hash != row.id_hash)):
            other.fcm_token = None
        db.flush()
    row.fcm_token = token or None
    row.platform, row.app_version = platform, app_version
    row.club_ids, row.announcements, row.notify_changes = json.dumps(sorted(set(clubs))), announcements, changes
    row.last_seen = _utcnow()
    db.commit()
