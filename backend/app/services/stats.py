"""Счётчик пользователей (админка → «Обзор» → «Пользователи»). Обезличенно: только хэши id установок, без IP/UA.
Сайт и PWA шлют POST /api/app/ping (раз в день и при возврате в приложение); APK учитывается по app_devices
(опрос объявлений / регистрация FCM) — пересборка APK не нужна, вид для них — android-apk."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Admin, AppDevice, Install, PushSubscription
from .broadcast import DEVICE_ACTIVE_DAYS, DEVICE_FORGET_DAYS

KINDS = ("web", "ios-pwa", "pwa")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def install_key(install_id: str) -> str:
    return hashlib.sha256(("install|" + install_id).encode()).hexdigest()


def ping(db: Session, install_id: str, kind: str) -> None:
    now = _utcnow()
    row = db.get(Install, install_key(install_id))
    if row is None:
        db.execute(delete(Install).where(Install.last_seen < now - timedelta(days=DEVICE_FORGET_DAYS)))
        row = Install(id_hash=install_key(install_id), kind=kind, first_seen=now)
        db.add(row)
    row.kind, row.last_seen = kind, now
    db.commit()


def summary(db: Session) -> dict:
    now = _utcnow()
    forget = now - timedelta(days=DEVICE_FORGET_DAYS)
    windows = {"day": now - timedelta(days=1), "week": now - timedelta(days=7), "month": now - timedelta(days=30)}
    groups = {"android-apk": [], "ios-pwa": [], "web": []}
    for d in db.scalars(select(AppDevice).where(AppDevice.last_seen >= forget)):
        groups["android-apk"].append((d.last_seen, None))
    for i in db.scalars(select(Install).where(Install.last_seen >= forget)):
        groups["ios-pwa" if i.kind == "ios-pwa" else "web"].append((i.last_seen, i.first_seen))
    active = {w: {k: sum(1 for ls, _ in rows if ls >= since) for k, rows in groups.items()} for w, since in windows.items()}
    for w in active:
        active[w]["total"] = sum(active[w].values())
    new_week = sum(1 for k in ("ios-pwa", "web") for _, fs in groups[k] if fs and fs >= windows["week"])
    fcm_since = now - timedelta(days=DEVICE_ACTIVE_DAYS)
    return {
        "total": sum(len(v) for v in groups.values()),
        "by_kind": {k: len(v) for k, v in groups.items()},
        "active": active,
        "new_week": new_week,
        "push": {"web": db.scalar(select(func.count(func.distinct(PushSubscription.endpoint)))) or 0,
                 "fcm": db.scalar(select(func.count()).select_from(AppDevice).where(
                     AppDevice.fcm_token.is_not(None), AppDevice.last_seen >= fcm_since)) or 0},
        "admins": db.scalar(select(func.count()).select_from(Admin)) or 0,
        "forget_days": DEVICE_FORGET_DAYS,
    }
