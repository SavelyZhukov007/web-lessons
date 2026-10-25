"""Firebase Cloud Messaging (HTTP v1) для APK.

Включается переменной FCM_CREDENTIALS_FILE — путь к JSON-ключу сервисного аккаунта Firebase (секрет: монтируется
на сервер отдельно, в репозиторий не попадает). Без неё (или если файла нет) FCM молча выключен — остальное работает,
APK получает объявления и изменения опросом. Сообщения только data (уведомление рисует приложение — общая
дедупликация с опросом), приоритет high, collapse_key = тег события.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("clubs.fcm")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
TTL_SECONDS = 24 * 3600

_lock = threading.Lock()
_creds = None
_creds_path: str | None = None
_project: str | None = None


class FcmGone(Exception):
    """Токен больше не действителен (UNREGISTERED / 404) — его надо удалить."""


def credentials_file() -> Path | None:
    raw = (os.getenv("FCM_CREDENTIALS_FILE") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def enabled() -> bool:
    return credentials_file() is not None


def reset() -> None:
    global _creds, _creds_path, _project
    with _lock:
        _creds = _creds_path = _project = None


def _load():
    """Учётные данные сервисного аккаунта (кэшируются; токен OAuth обновляется google-auth по сроку)."""
    global _creds, _creds_path, _project
    path = credentials_file()
    if path is None:
        raise RuntimeError("FCM не настроен")
    with _lock:
        if _creds is None or _creds_path != str(path):
            from google.oauth2 import service_account

            info = json.loads(path.read_text(encoding="utf-8"))
            _creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
            _project = os.getenv("FCM_PROJECT_ID") or info.get("project_id")
            _creds_path = str(path)
        return _creds, _project


def _access_token() -> tuple[str, str]:
    creds, project = _load()
    if not creds.valid:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    return creds.token, project


def _post(url: str, headers: dict, body: dict):
    import requests

    return requests.post(url, headers=headers, json=body, timeout=10)


def message(token: str, data: dict, collapse: str | None = None) -> dict:
    android = {"priority": "HIGH", "ttl": f"{TTL_SECONDS}s"}
    if collapse:
        android["collapse_key"] = collapse[:64]
    return {"message": {"token": token, "data": {k: "" if v is None else str(v) for k, v in data.items()}, "android": android}}


def _is_gone(status: int, body: dict) -> bool:
    if status == 404:
        return True
    err = (body or {}).get("error") or {}
    if err.get("status") == "NOT_FOUND":
        return True
    for d in err.get("details") or []:
        if d.get("errorCode") == "UNREGISTERED":
            return True
    return False


def send_one(token: str, data: dict, collapse: str | None = None) -> None:
    """Одно data-сообщение. Единственное место с сетевым вызовом FCM (в тестах подменяется _post)."""
    access, project = _access_token()
    r = _post(SEND_URL.format(project=project), {"Authorization": f"Bearer {access}", "Content-Type": "application/json; UTF-8"},
              message(token, data, collapse))
    if 200 <= r.status_code < 300:
        return
    try:
        body = r.json()
    except ValueError:
        body = {}
    if _is_gone(r.status_code, body):
        raise FcmGone(str(r.status_code))
    raise RuntimeError(f"FCM HTTP {r.status_code}: {str(body)[:200]}")
