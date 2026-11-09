"""Push о новой версии. Когда в каталоге релизов (APP_RELEASES_DIR: latest.json + сам APK) появляется versionCode выше
последнего оповещённого, уходит ровно одна рассылка на версию (последний оповещённый versionCode хранится рядом с БД,
поэтому переживает перезапуски; первый запуск только запоминает текущую версию):
* announcement «auto» в frontend/release-info.json и latest.json — объявление «Что нового в KipClub vX» с текстом выката
  для всех платформ (веб, iPhone PWA, APK) с учётом «Объявлений»; APK с выключенными объявлениями получает служебный
  update-available. Скрипт выката (tools/ops/deploy-release.sh) вызывает `server.py announce-release` сразу после
  публикации, фоновая проверка — страховка; повтор не дублирует рассылку (idempotency_key release:vX);
* «manual» — только запоминание, объявление отправляет оператор командой `server.py announce-release vX --send`;
* иначе — только update-available в APK (FCM)."""
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
        mode = rel.get("announcement")
        if mode == "manual":
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
        announced = None
        if mode == "auto":
            # Выкат с текстом «Что нового»: одно объявление на все платформы (веб, iPhone PWA, APK) с учётом
            # «Объявлений». APK с выключенными объявлениями всё равно получает служебный push об обновлении.
            try:
                announced = announce(db, _release_tag(rel))
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("объявление о выпуске %s: сбой", name)
        try:
            # только APK: web-подписчикам сайта обновление APK не нужно
            delivery._send_fcm(db, ev, r, only=(lambda d: not d.announcements) if announced else None)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("push об обновлении %s: сбой", name)
        log.info("push об обновлении %s (versionCode %s): отправлено %s, ошибок %s", name, code, r.fcm_sent, r.fcm_failed)
        out = {"versionCode": code, "fcm_sent": r.fcm_sent, "fcm_failed": r.fcm_failed}
        if announced is not None:
            out["announcement"] = announced
        return out


def _release_tag(release: dict) -> str:
    """«v1.9.016prA» → «v1.9.016»: номер выпуска из release-info.json без канала и платформы."""
    import re

    raw = str(release.get("versionName") or release.get("version") or "")
    match = re.match(r"v?(\d+\.\d+\.\d+)", raw)
    if not match:
        raise ValueError(f"Не удалось понять версию выпуска: {raw!r}")
    return "v" + match.group(1)


def announcement_text(version: str, changelog: list[str], limit: int = 230) -> tuple[str, str]:
    """Заголовок и текст push «Что нового»: пункты списка изменений, пока помещаются в limit символов."""
    title = f"Что нового в KipClub {version}"
    items = [str(item).strip() for item in changelog if str(item).strip()]
    body = ""
    for item in items:
        candidate = f"{body} · {item}" if body else item
        if len(candidate) > limit:
            break
        body = candidate
    if not body and items:
        body = items[0][: limit - 1].rstrip() + "…"
    elif body and len(body) < len(" · ".join(items)):
        body += " · и другое"
    return title, body or f"KipClub обновился до {version}. Посмотрите, что нового."



def announce(db: Session, version: str) -> dict:
    """Publish a single release announcement only after the operator has accepted the deployment."""
    from ..routers.distribution import _frontend, latest_release

    notes = json.loads((_frontend() / "release-info.json").read_text(encoding="utf-8"))
    release = latest_release()
    mode = notes.get("announcement")
    if (notes.get("version") != version or mode not in ("manual", "auto")
            or release is None or release.get("announcement") != mode
            or not release["versionName"].startswith(version)
            or release["changelog"] != notes.get("changelog")):
        raise ValueError("APK и веб-версия не совпадают со списком изменений")

    key = f"release:{version}"
    title, body = announcement_text(version, notes.get("changelog") or [])
    result = db.execute(insert(Broadcast).values(
        title=title, body=body,
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
