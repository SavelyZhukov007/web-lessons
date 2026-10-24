"""Лимит неудачных входов в БД (SEC-03). Скользящее окно: MAX_ATTEMPTS за WINDOW по ключу (ip, login)
+ общий потолок на IP, чтобы нельзя было перебирать разные логины."""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models.login_attempt import LoginAttempt

MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
WINDOW = timedelta(minutes=int(os.getenv("LOGIN_WINDOW_MINUTES", "15")))
MAX_ATTEMPTS_PER_IP = int(os.getenv("LOGIN_MAX_ATTEMPTS_PER_IP", "30"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _retry_after(db: Session, *conds, limit: int) -> int | None:
    """None — не заблокирован; иначе секунды до освобождения (когда самая старая из `limit` последних попыток выйдет из окна)."""
    since = utcnow() - WINDOW
    times = list(
        db.scalars(
            select(LoginAttempt.attempted_at)
            .where(LoginAttempt.attempted_at > since, *conds)
            .order_by(LoginAttempt.attempted_at.desc())
            .limit(limit)
        )
    )
    if len(times) < limit:
        return None
    unlock = times[-1] + WINDOW
    return max(1, math.ceil((unlock - utcnow()).total_seconds()))


def retry_after(db: Session, ip: str, login: str) -> int | None:
    a = _retry_after(db, LoginAttempt.ip == ip, LoginAttempt.login == login, limit=MAX_ATTEMPTS)
    b = _retry_after(db, LoginAttempt.ip == ip, limit=MAX_ATTEMPTS_PER_IP)
    waits = [x for x in (a, b) if x is not None]
    return max(waits) if waits else None


def record_failure(db: Session, ip: str, login: str) -> None:
    db.add(LoginAttempt(ip=ip[:64], login=login[:64]))
    db.commit()


def clear(db: Session, ip: str, login: str) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.ip == ip, LoginAttempt.login == login))
    db.commit()


def purge_old(db: Session) -> int:
    n = db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < utcnow() - WINDOW * 2)).rowcount
    db.commit()
    return n or 0


def count_recent(db: Session, ip: str, login: str) -> int:
    since = utcnow() - WINDOW
    return db.scalar(
        select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.ip == ip, LoginAttempt.login == login, LoginAttempt.attempted_at > since
        )
    ) or 0
