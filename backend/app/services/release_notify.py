"""Автоматический push о новой версии APK. Когда в каталоге релизов (APP_RELEASES_DIR: latest.json + сам APK) появляется
versionCode выше последнего оповещённого, всем активным установкам с FCM уходит одно data-сообщение update-available
(нажатие открывает приложение на /?update=1 — экран обновления). Последний оповещённый versionCode хранится в файле
рядом с БД (/data), поэтому переживает перезапуски. Первый запуск только запоминает текущую версию — без рассылки."""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models.broadcast import Broadcast
from . import audit, broadcast, delivery

log = logging.getLogger("clubs.release_notify")
CHECK_INTERVAL = 300
_lock = threading.Lock()


def state_file() -> Path:
    from ..database import DB_PATH
    return Path(os.getenv("RELEASE_NOTIFY_STATE") or Path(DB_PATH).with_name("release-notified.json"))


def _read() -> int | None:
    try:
        return int(json.loads(state_file().read_text(encoding="utf-8"))["versionCode"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write(code: int) -> None:
    path = state_file()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"versionCode": code}) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def check(db: Session) -> dict | None:
    """Возвращает итог рассылки (или None, если слать нечего). Не бросает исключений наружу из фоновой задачи."""
    from ..routers.distribution import latest_release
    with _lock:
        rel = latest_release()
        code = rel and rel.get("versionCode")
        if not code:
            return None
        last = _read()
        if rel.get("announcement") == "manual":
            if last is None or code > last:
                _write(code)
            return None
        if last is None:  # первый запуск: текущая версия уже у всех — только запоминаем
            _write(code)
            return None
        if code <= last:
            return None
        _write(code)  # сначала фиксируем — ровно один раз на версию, даже если отправка упадёт посередине
        version = str(rel.get("version") or code)
        name = version if version.startswith("v") else "v" + version
        ev = delivery.Event(kind="update-available", audience="all", club_ids=[],
                            payload={"title": "KipClub", "body": f"Доступно обновление {name}", "url": "/?update=1", "tag": f"update-{code}"},
                            data={"version": version, "versionCode": str(code)})
        r = delivery.Result()
        try:
            delivery._send_fcm(db, ev, r)  # только APK: web-подписчикам сайта обновление APK не нужно
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("push об обновлении %s: сбой", name)
        log.info("push об обновлении %s (versionCode %s): отправлено %s, ошибок %s", name, code, r.fcm_sent, r.fcm_failed)
        return {"versionCode": code, "fcm_sent": r.fcm_sent, "fcm_failed": r.fcm_failed}



def announce(db: Session, version: str) -> dict:
    """Publish a single release announcement only after the operator has accepted the deployment."""
    from ..routers.distribution import _frontend, latest_release

    notes = json.loads((_frontend() / "release-info.json").read_text(encoding="utf-8"))
    release = latest_release()
    if (notes.get("version") != version or notes.get("announcement") != "manual"
            or release is None or release.get("announcement") != "manual"
            or not release["versionName"].startswith(version)
            or release["changelog"] != notes.get("changelog")):
        raise ValueError("APK и веб-версия не совпадают со списком изменений")

    key = f"release:{version}"
    result = db.execute(insert(Broadcast).values(
        title="KipClub", body=f"KipClub обновился до {version}. Посмотрите, что нового.",
        url=f"/?update=1&release={version}", audience="all", club_ids="[]", session_ids="[]",
        author_login="KipClub", idempotency_key=key,
        web_sent=-1, web_failed=-1, fcm_sent=-1, fcm_failed=-1, apk_targets=-1,
    ).on_conflict_do_nothing(index_elements=[Broadcast.idempotency_key]))
    inserted = result.rowcount == 1
    db.commit()
    row = db.scalar(select(Broadcast).where(Broadcast.idempotency_key == key))
    if inserted:
        broadcast.dispatch(db, row)
        audit.log("release_announcement", version=version, broadcast_id=row.id,
                  web_sent=row.web_sent, web_failed=row.web_failed, fcm_sent=row.fcm_sent,
                  fcm_failed=row.fcm_failed, apk_targets=row.apk_targets)
    return {
        "version": version, "broadcast_id": row.id, "duplicate": not inserted,
        "dispatch": "recorded" if row.apk_targets >= 0 else "unconfirmed",
        "web_sent": row.web_sent, "web_failed": row.web_failed, "fcm_sent": row.fcm_sent,
        "fcm_failed": row.fcm_failed, "apk_targets": row.apk_targets,
    }
