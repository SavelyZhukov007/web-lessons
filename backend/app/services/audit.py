"""Аудит действий админа и событий входа (OPS-03). Пишет структурную строку в logger `clubs.audit`
(+ опционально в файл AUDIT_LOG_FILE). Пароли/токены сюда не попадают — только идентификаторы."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .. import settings

logger = logging.getLogger("clubs.audit")
_file_handler_for: str | None = None


def _ensure_file_handler() -> None:
    global _file_handler_for
    path = settings.audit_log_path()
    if path and _file_handler_for != path:
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _file_handler_for = path


def log(event: str, **fields) -> None:
    _ensure_file_handler()
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
    try:
        logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001 — аудит не должен ломать запрос
        pass
