"""«Обратная связь» (только для разработчиков): проверка и сохранение отчёта на диск. БД не используется — папки и есть источник.

FEEDBACK_DIR/<YYYY-MM-DD_HHMMSS>_<type>_<short id>/
    report.json, description.md, logs.json, screenshots/01.png…, manifest.json (uuid, created_at, sha256 + размер каждого файла)
Запись — во временную папку .tmp-<uuid> и атомарное переименование; manifest.json пишется последним.
После сохранения остаются только последние FEEDBACK_KEEP (по умолчанию 50) готовых папок.
Выгрузка на компьютер разработчика — tools/feedback_export.py (по SSH, только чтение).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path

from .. import settings
from .client_logs import redact

TYPES = ("idea", "bug", "question", "other")
DESC_MIN, DESC_MAX = 10, 2000
MAX_SHOTS, MAX_SHOT = 5, 5 * 1024 * 1024
MAX_LOGS = 512 * 1024
MAX_BODY = MAX_SHOTS * MAX_SHOT + MAX_LOGS + 256 * 1024
RATE, WINDOW = 5, 3600
TMP_PREFIX = ".tmp-"
MANIFEST = "manifest.json"
_EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}
_CONTACT = re.compile(r"^([^@\s]{1,64}@[^@\s]{1,100}\.[A-Za-z]{2,}|@?[A-Za-z0-9_]{4,32}|(https?://)?t\.me/[A-Za-z0-9_]{4,32})$")
_lock = threading.Lock()
_save_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


class FeedbackError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def allow(key: str, now: float | None = None) -> bool:
    """Частота: RATE отчётов за WINDOW секунд на ключ (в памяти процесса; один воркер — см. docs/deploy.md)."""
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits[key]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= RATE:
            return False
        q.append(now)
        if len(_hits) > 10000:
            for k in [k for k, v in _hits.items() if not v][:5000]:
                _hits.pop(k, None)
        return True


def reset_limits() -> None:
    with _lock:
        _hits.clear()


def sniff_image(data: bytes) -> str | None:
    """Тип по магическим байтам (не по имени/Content-Type)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def parse_form(content_type: str, body: bytes) -> tuple[dict[str, str], list[bytes]]:
    """multipart/form-data (или urlencoded без файлов) без внешних зависимостей. Файлы поля screenshots — байты."""
    ct = content_type.lower()
    if ct.startswith("application/x-www-form-urlencoded"):
        from urllib.parse import parse_qsl
        return dict(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True)), []
    if not ct.startswith("multipart/form-data"):
        raise FeedbackError("Ожидался multipart/form-data")
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not msg.is_multipart():
        raise FeedbackError("Некорректный multipart")
    fields: dict[str, str] = {}
    files: list[bytes] = []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True) or b""
        if name == "screenshots":
            if data:
                files.append(data)
        elif name:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def _json(raw: str, limit: int, default):
    if not raw:
        return default
    if len(raw.encode()) > limit:
        raise FeedbackError("Слишком большие логи", 413)
    try:
        return json.loads(raw)
    except ValueError:
        raise FeedbackError("Логи/метаданные должны быть JSON") from None


def validate(fields: dict[str, str], files: list[bytes]) -> dict:
    kind = fields.get("type", "").strip()
    if kind not in TYPES:
        raise FeedbackError("Выберите тип обращения")
    desc = fields.get("description", "").strip()
    if not DESC_MIN <= len(desc) <= DESC_MAX:
        raise FeedbackError(f"Описание: от {DESC_MIN} до {DESC_MAX} символов")
    contact = fields.get("contact", "").strip() or None
    if contact and (len(contact) > 100 or not _CONTACT.match(contact)):
        raise FeedbackError("Контакт: e-mail или Telegram (@username)")
    if len(files) > MAX_SHOTS:
        raise FeedbackError(f"Не больше {MAX_SHOTS} скриншотов")
    shots = []
    for data in files:
        if len(data) > MAX_SHOT:
            raise FeedbackError("Скриншот больше 5 МБ", 413)
        kind_img = sniff_image(data)
        if not kind_img:
            raise FeedbackError("Скриншоты: только PNG, JPEG или WebP", 415)
        shots.append((_EXT[kind_img], data))
    meta = _json(fields.get("meta", ""), 32 * 1024, {})
    logs = _json(fields.get("logs", ""), MAX_LOGS, None)  # клиент шлёт всегда; без логов — тоже принимаем
    if not isinstance(meta, dict):
        meta = {}
    if logs is not None and not isinstance(logs, (list, dict)):
        logs = None
    return {"type": kind, "description": desc, "contact": contact, "shots": shots, "meta": meta, "logs": logs}


def _redact_tree(v):
    if isinstance(v, str):
        return redact(v)[:4000]
    if isinstance(v, list):
        return [_redact_tree(x) for x in v[:1000]]
    if isinstance(v, dict):
        return {str(k)[:60]: _redact_tree(x) for k, x in list(v.items())[:200]}
    return v


def _platform(meta: dict) -> str:
    p = str(meta.get("platform", "")).upper()[:1]
    return p if p in ("W", "M", "A") else ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path, report_id: str, created_at: str, folder: str) -> dict:
    files = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel != MANIFEST:
            files[rel] = {"sha256": _sha256(p), "size": p.stat().st_size}
    return {"id": report_id, "created_at": created_at, "folder": folder, "files": files}


def complete_folders(base: Path) -> list[Path]:
    """Готовые отчёты (есть manifest.json), от старых к новым."""
    if not base.is_dir():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".") and (p / MANIFEST).is_file()), key=lambda p: p.name)


def prune(base: Path, keep: int | None = None) -> list[str]:
    """Удаляет самые старые готовые папки сверх лимита и брошенные .tmp-* старше часа. Возвращает удалённые имена."""
    keep = settings.feedback_keep() if keep is None else keep
    removed = []
    for p in complete_folders(base)[:-keep] if keep > 0 else []:
        shutil.rmtree(p, ignore_errors=True)
        removed.append(p.name)
    if base.is_dir():
        for p in base.glob(TMP_PREFIX + "*"):
            try:
                if time.time() - p.stat().st_mtime > 3600:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    return removed


def save(data: dict, host: str = "", now: datetime | None = None) -> dict:
    """Пишет отчёт во временную папку и атомарно переименовывает; затем чистит старые. Возвращает manifest."""
    base = settings.feedback_dir()
    base.mkdir(parents=True, exist_ok=True)
    created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rid = str(uuid.uuid4())
    folder = f"{created:%Y-%m-%d_%H%M%S}_{data['type']}_{rid[:8]}"
    created_iso = created.isoformat(timespec="seconds")
    meta = _redact_tree(data["meta"])
    tmp = base / f"{TMP_PREFIX}{rid}"
    try:
        (tmp / "screenshots").mkdir(parents=True)
        names = []
        for i, (ext, blob) in enumerate(data["shots"], 1):
            name = f"{i:02d}.{ext}"
            (tmp / "screenshots" / name).write_bytes(blob)
            names.append(name)
        report = {"id": rid, "type": data["type"], "created_at": created_iso, "app_version": str(meta.get("version", ""))[:40],
                  "platform": _platform(meta), "contact": data["contact"], "screenshots": names, "logs_attached": data["logs"] is not None,
                  "server": {"env": settings.env(), "name": settings.server_name(), "host": host[:120]}, "client": meta}
        (tmp / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (tmp / "description.md").write_text(f"# Обратная связь ({data['type']})\n\n{data['description']}\n", encoding="utf-8")
        logs = _redact_tree(data["logs"]) if data["logs"] is not None else []
        (tmp / "logs.json").write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = build_manifest(tmp, rid, created_iso, folder)
        (tmp / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with _save_lock:
            os.replace(tmp, base / folder)
            prune(base)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return manifest
