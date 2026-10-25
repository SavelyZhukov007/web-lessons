"""Журнал ошибок клиентов (приложение): JSONL по дням в APP_LOGS_DIR, срок хранения LOGS_RETENTION_DAYS.

Ограничения: тело запроса ≤ MAX_BODY, ≤ MAX_ENTRIES записей, строка ≤ MAX_MSG; частота — RATE на IP/устройство
за WINDOW секунд (в памяти процесса). Секреты (токены, пароли, Authorization) вырезаются ещё раз на сервере.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import settings

MAX_BODY = 256 * 1024
MAX_ENTRIES = 500
MAX_MSG = 4000
RATE, WINDOW = 30, 600
LEVELS = ("debug", "info", "warn", "error")
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)

_REDACT = [
    (re.compile(r"(?i)(authorization\"?\s*[:=]\s*\"?)(bearer\s+)?[^\s\",;]+"), r"\1[скрыто]"),
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"), "Bearer [скрыто]"),
    (re.compile(r"(?i)((?:password|passwd|пароль|token|access_token|refresh_token|secret|api_key)\"?\s*[:=]\s*\"?)[^\s\",&;]+"), r"\1[скрыто]"),
    (re.compile(r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}"), "[jwt скрыт]"),
    (re.compile(r"(?i)\bT(?:[-\s]*[A-Z2-7]){26}\b"), "[teacher id скрыт]"),
    (re.compile(r"(?i)\b[A-Z2-7]{26}\b"), "[teacher id скрыт]"),
]


def redact(text: str) -> str:
    for rx, rep in _REDACT:
        text = rx.sub(rep, text)
    return text


def allow(key: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits[key]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= RATE:
            return False
        q.append(now)
        if len(_hits) > 10000:  # не растём бесконечно
            for k in [k for k, v in _hits.items() if not v][:5000]:
                _hits.pop(k, None)
        return True


def reset_limits() -> None:
    with _lock:
        _hits.clear()


def _clean(v, n=MAX_MSG) -> str:
    return redact(str(v if v is not None else ""))[:n]


def normalize(entry: dict, meta: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None
    level = str(entry.get("level", "info")).lower()
    level = level if level in LEVELS else "info"
    t = entry.get("t")
    try:
        ts = datetime.fromtimestamp(float(t) / 1000, tz=timezone.utc) if isinstance(t, (int, float)) else datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    out = {"t": ts.astimezone(timezone.utc).isoformat(timespec="milliseconds"), "level": level,
           "kind": _clean(entry.get("kind", ""), 40), "msg": _clean(entry.get("msg", "")),
           **{k: _clean(meta.get(k), 120) for k in ("device", "version", "platform", "os", "webview")}}
    if entry.get("stack"):
        out["stack"] = _clean(entry["stack"])
    for k in ("url", "status", "page"):
        if entry.get(k) is not None:
            out[k] = _clean(entry[k], 300)
    return out


def _file(day: date) -> Path:
    return settings.logs_dir() / f"client-{day.isoformat()}.jsonl"


def append(entries: list[dict]) -> int:
    if not entries:
        return 0
    d = settings.logs_dir()
    d.mkdir(parents=True, exist_ok=True)
    with _lock, _file(datetime.now(timezone.utc).date()).open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    cleanup()
    return len(entries)


def cleanup(today: date | None = None) -> int:
    """Удаляет файлы старше срока хранения. Возвращает число удалённых."""
    today = today or datetime.now(timezone.utc).date()
    limit = today - timedelta(days=settings.logs_retention_days())
    n = 0
    d = settings.logs_dir()
    if not d.is_dir():
        return 0
    for p in d.glob("client-*.jsonl"):
        try:
            if date.fromisoformat(p.stem[7:]) < limit:
                p.unlink()
                n += 1
        except (ValueError, OSError):
            continue
    return n


def query(level: str | None = None, version: str | None = None, device: str | None = None,
          date_from: date | None = None, date_to: date | None = None, limit: int = 1000) -> list[dict]:
    d = settings.logs_dir()
    if not d.is_dir():
        return []
    files = sorted(d.glob("client-*.jsonl"), reverse=True)
    min_level = LEVELS.index(level) if level in LEVELS else 0
    out: list[dict] = []
    for p in files:
        try:
            day = date.fromisoformat(p.stem[7:])
        except ValueError:
            continue
        if (date_from and day < date_from) or (date_to and day > date_to):
            continue
        for line in reversed(p.read_text(encoding="utf-8").splitlines()):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if LEVELS.index(e.get("level", "info")) < min_level:
                continue
            if version and e.get("version") != version:
                continue
            if device and not str(e.get("device", "")).startswith(device):
                continue
            out.append(e)
            if len(out) >= limit:
                return out
    return out


def as_text(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        head = f"{e['t']} {e['level'].upper():5} [{e.get('kind', '')}] v{e.get('version', '?')} {e.get('platform', '')} {e.get('device', '')[:8]}"
        extra = " ".join(f"{k}={e[k]}" for k in ("status", "url", "page") if e.get(k))
        lines.append(f"{head} {e['msg']}" + (f" ({extra})" if extra else ""))
        if e.get("stack"):
            lines.extend("    " + s for s in e["stack"].splitlines()[:20])
    return "\n".join(lines) + ("\n" if lines else "")
