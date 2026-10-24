"""Web Push: VAPID-ключи, рассылка при отмене/переносе занятия.

Ничего отсюда не должно ломать основной запрос: notify_exception вызывается из BackgroundTasks
и глотает все ошибки (пишет в лог)."""
from __future__ import annotations

import base64
import json
import logging
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import delete, or_, select

from ..database import ROOT, SessionLocal
from ..models.push_subscription import PushSubscription
from ..models.session_exception import SessionException

log = logging.getLogger("clubs.push")

# Разрешённые push-сервисы (защита от SSRF: сервер сам делает POST на endpoint из запроса).
DEFAULT_ALLOWED_HOSTS = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    ".push.apple.com",
    ".notify.windows.com",
)

_keys_lock = threading.Lock()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class VapidKeys:
    private_key: str  # urlsafe-base64 32-байтового скаляра P-256
    public_key: str  # urlsafe-base64 несжатой точки (то, что ждёт applicationServerKey)


def _keys_from_private_b64(private_b64: str) -> VapidKeys:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = base64.urlsafe_b64decode(private_b64 + "=" * (-len(private_b64) % 4))
    key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
    pub = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return VapidKeys(_b64url(raw), _b64url(pub))


def keys_file() -> Path:
    custom = os.getenv("VAPID_KEYS_FILE")
    return Path(custom) if custom else ROOT / "vapid_keys.json"


def get_vapid_keys() -> VapidKeys:
    """env VAPID_PRIVATE_KEY (base64url) → иначе файл VAPID_KEYS_FILE (по умолчанию ./vapid_keys.json,
    в .gitignore) → иначе генерируем один раз и сохраняем с правами 600."""
    env_private = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if env_private:
        return _keys_from_private_b64(env_private)
    with _keys_lock:
        path = keys_file()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return _keys_from_private_b64(data["private_key"])
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.private_numbers().private_value.to_bytes(32, "big")
        keys = _keys_from_private_b64(_b64url(raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"private_key": keys.private_key, "public_key": keys.public_key}),
            encoding="utf-8",
        )
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # на Windows почти no-op
        except OSError:
            pass
        return keys


def vapid_subject() -> str:
    return os.getenv("VAPID_SUBJECT", "mailto:admin@example.org")


def _extra_hosts() -> tuple[str, ...]:
    raw = os.getenv("PUSH_ALLOWED_HOSTS", "")
    return tuple(h.strip().lower() for h in raw.split(",") if h.strip())


def _host_matches(host: str, rule: str) -> bool:
    return host == rule or (rule.startswith(".") and host.endswith(rule))


def endpoint_allowed(endpoint: str) -> bool:
    """https + известный push-сервис. PUSH_ALLOWED_HOSTS (через запятую) добавляет свои хосты
    (для них разрешён и http — например локальный тестовый стенд)."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if any(_host_matches(host, rule) for rule in DEFAULT_ALLOWED_HOSTS):
        return parts.scheme == "https"
    return parts.scheme in ("http", "https") and any(_host_matches(host, rule) for rule in _extra_hosts())


class PushGone(Exception):
    """Подписка мертва (HTTP 404/410) — её надо удалить."""


def send_one(subscription_info: dict, payload: dict) -> None:
    """Отправляет одно уведомление. Единственное место, где вызывается pywebpush (в тестах подменяется)."""
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    keys = get_vapid_keys()
    vapid = Vapid.from_raw(keys.private_key.encode("ascii"))
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid,
            vapid_claims={"sub": vapid_subject()},
            ttl=24 * 3600,
            timeout=10,
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushGone(str(exc)) from exc
        raise


def _fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}"


def build_payload(exception: SessionException) -> dict:
    session = exception.session
    club = session.club
    comment = f" {exception.comment.strip()}" if (exception.comment or "").strip() else ""
    if exception.type == "cancelled":
        title = f"Занятие отменено: {club.name}"
        body = f"{_fmt_date(exception.original_date)}, {session.start_time}–{session.end_time}.{comment}"
    else:
        room = exception.new_room
        room_text = f", {room.name}" if room else ""
        title = f"Занятие перенесено: {club.name}"
        body = (
            f"Было {_fmt_date(exception.original_date)} {session.start_time}; "
            f"стало {_fmt_date(exception.new_date)} {exception.new_start_time}–{exception.new_end_time}"
            f"{room_text}.{comment}"
        )
    return {
        "title": title,
        "body": body.strip(),
        "url": f"/club.html?id={club.id}",
        "tag": f"exception-{exception.id}",
        "kind": exception.type,
        "club_id": club.id,
    }


def notify_exception(exception_id: int) -> int:
    """Рассылает уведомление подписчикам клуба (и подписчикам «все кружки»). Возвращает число отправленных.
    Никогда не бросает исключений."""
    sent = 0
    try:
        with SessionLocal() as db:
            exception = db.get(SessionException, exception_id)
            if exception is None:
                return 0
            payload = build_payload(exception)
            subs = list(
                db.scalars(
                    select(PushSubscription).where(
                        or_(
                            PushSubscription.club_id == payload["club_id"],
                            PushSubscription.club_id.is_(None),
                        )
                    )
                )
            )
            seen: set[str] = set()  # один endpoint — одно уведомление, даже если подписан и на клуб, и на «все»
            dead: list[int] = []
            for sub in subs:
                if sub.endpoint in seen:
                    continue
                seen.add(sub.endpoint)
                try:
                    send_one(
                        {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                        payload,
                    )
                    sent += 1
                except PushGone:
                    dead.append(sub.id)
                    dead.extend(s.id for s in subs if s.endpoint == sub.endpoint and s.id != sub.id)
                except Exception:  # noqa: BLE001 — одна плохая подписка не должна ломать остальные
                    log.exception("push: не удалось отправить на %s…", sub.endpoint[:60])
            if dead:
                db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
                db.commit()
    except Exception:  # noqa: BLE001
        log.exception("push: сбой рассылки для исключения %s", exception_id)
    return sent
