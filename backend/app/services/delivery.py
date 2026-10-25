"""Единая доставка уведомлений по всем каналам: Web Push (браузер/PWA) и FCM (APK).

Используется и при отмене/переносе (push.notify_exception), и для объявлений (broadcast.dispatch).
APK без FCM получает то же самое опросом (SyncWorker / GET /api/announcements) — на устройстве общая дедупликация.
Ничего не бросает: одна плохая подписка не мешает остальным.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models.broadcast import AppDevice
from ..models.push_subscription import PushSubscription
from . import fcm
from . import push as push_service

log = logging.getLogger("clubs.delivery")
DEVICE_ACTIVE_DAYS = 60   # FCM-токен старше — не трогаем (установку, скорее всего, удалили)
CHANGE_KINDS = ("cancel", "reschedule", "schedule-change")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ids(raw: str | None) -> set[int]:
    try:
        return {int(x) for x in json.loads(raw or "[]")}
    except (ValueError, TypeError):
        return set()


@dataclass
class Event:
    kind: str                      # cancel | reschedule | announcement | schedule-change | update-available
    audience: str                  # all | clubs
    club_ids: list[int]
    payload: dict                  # для Web Push (title, body, url, tag, ...)
    data: dict = field(default_factory=dict)  # для FCM (строки), type/tag добавляются сами

    @property
    def tag(self) -> str:
        return str(self.payload.get("tag") or self.kind)


@dataclass
class Result:
    web_sent: int = 0
    web_failed: int = 0
    fcm_sent: int = 0
    fcm_failed: int = 0


def web_targets(db: Session, ev: Event) -> list[PushSubscription]:
    stmt = select(PushSubscription)
    if ev.kind == "announcement":
        stmt = stmt.where(PushSubscription.announcements.is_(True))
    if ev.audience != "all":
        stmt = stmt.where(or_(PushSubscription.club_id.in_(ev.club_ids), PushSubscription.club_id.is_(None)))
    seen: set[str] = set()
    out = []
    for sub in db.scalars(stmt.order_by(PushSubscription.id)):
        if sub.endpoint not in seen:  # одно устройство — одно уведомление
            seen.add(sub.endpoint)
            out.append(sub)
    return out


def device_matches(ev: Event, d: AppDevice) -> bool:
    clubs = _ids(d.club_ids)
    if ev.kind == "announcement":
        return bool(d.announcements) and (ev.audience == "all" or bool(clubs & set(ev.club_ids)))
    if ev.kind in CHANGE_KINDS:  # как на устройстве: изменения только по «моим кружкам»
        return bool(d.notify_changes) and bool(clubs & set(ev.club_ids))
    return True


def fcm_targets(db: Session, ev: Event) -> list[AppDevice]:
    since = _utcnow() - timedelta(days=DEVICE_ACTIVE_DAYS)
    rows = db.scalars(select(AppDevice).where(AppDevice.fcm_token.is_not(None), AppDevice.last_seen >= since))
    return [d for d in rows if device_matches(ev, d)]


def _send_web(db: Session, ev: Event, r: Result) -> None:
    dead: list[str] = []
    for sub in web_targets(db, ev):
        try:
            push_service.send_one({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, ev.payload)
            r.web_sent += 1
        except push_service.PushGone:
            dead.append(sub.endpoint)
            r.web_failed += 1
        except Exception:  # noqa: BLE001
            log.exception("web push (%s): не удалось отправить на %s…", ev.tag, sub.endpoint[:60])
            r.web_failed += 1
    if dead:
        db.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(dead)))
        db.commit()


def _send_fcm(db: Session, ev: Event, r: Result) -> None:
    if not fcm.enabled():
        return
    data = {"type": ev.kind, "tag": ev.tag, "title": ev.payload.get("title", ""), "body": ev.payload.get("body", ""),
            "url": ev.payload.get("url") or "/", **ev.data}
    dead: list[str] = []
    for d in fcm_targets(db, ev):
        try:
            fcm.send_one(d.fcm_token, data, ev.tag)
            r.fcm_sent += 1
        except fcm.FcmGone:
            dead.append(d.id_hash)
            r.fcm_failed += 1
        except Exception:  # noqa: BLE001
            log.exception("fcm (%s): не удалось отправить", ev.tag)
            r.fcm_failed += 1
    if dead:  # установку не удаляем — она может продолжать опрос; забываем только токен
        for d in db.scalars(select(AppDevice).where(AppDevice.id_hash.in_(dead))):
            d.fcm_token = None
        db.commit()


def deliver(db: Session, ev: Event) -> Result:
    r = Result()
    for name, channel in (("web", _send_web), ("fcm", _send_fcm)):
        try:
            channel(db, ev, r)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("доставка %s: сбой канала %s", ev.tag, name)
    return r


def estimate_fcm(db: Session, ev: Event) -> int:
    return len(fcm_targets(db, ev)) if fcm.enabled() else 0
