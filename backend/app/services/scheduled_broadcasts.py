"""Persistent at-most-once scheduled publication. Uncertain interrupted sends never auto-repeat."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Broadcast, BroadcastSchedule, Club, ClubSession
from ..schemas.broadcast import BroadcastCreate
from . import audit, broadcast


def read(row):
    data = json.loads(row.payload_json)
    return {
        **data,
        "id": "schedule-" + row.id,
        "schedule_id": row.id,
        "status": row.status,
        "scheduled_at": row.scheduled_at.isoformat() + "Z",
        "created_at": row.created_at.isoformat() + "Z",
        "author": row.author_login,
        "broadcast_id": row.broadcast_id,
        "error": row.error,
        "web_sent": 0,
        "web_failed": 0,
        "fcm_sent": 0,
        "fcm_failed": 0,
        "apk_targets": 0,
    }


def create(db: Session, payload: BroadcastCreate, admin):
    when = payload.scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)
    now = broadcast._utcnow()
    if not now + timedelta(seconds=30) <= when <= now + timedelta(days=366):
        raise ValueError("Отправка — не раньше чем через 30 секунд и не дальше чем через год")
    row = BroadcastSchedule(
        id=secrets.token_hex(16),
        idempotency_key=payload.idempotency_key,
        payload_json=json.dumps(payload.model_dump(mode="json", exclude={"scheduled_at"}), ensure_ascii=False),
        scheduled_at=when,
        author_id=admin.id,
        author_login=admin.login,
    )
    db.add(row)
    db.commit()
    return row


def run(db: Session, now=None):
    now = now or broadcast._utcnow()
    # A crash cannot prove which external providers accepted a payload. Never retry such a send blindly.
    db.execute(
        update(BroadcastSchedule)
        .where(BroadcastSchedule.status == "sending", BroadcastSchedule.updated_at < now - timedelta(minutes=5))
        .values(status="uncertain", error="Отправка прервана. Проверьте журнал перед ручным повтором.", updated_at=now)
    )
    db.commit()
    due = list(
        db.scalars(
            select(BroadcastSchedule.id)
            .where(BroadcastSchedule.status == "scheduled", BroadcastSchedule.scheduled_at <= now)
            .order_by(BroadcastSchedule.scheduled_at)
            .limit(10)
        )
    )
    for key in due:
        claimed = db.execute(
            update(BroadcastSchedule)
            .where(BroadcastSchedule.id == key, BroadcastSchedule.status == "scheduled")
            .values(status="sending", updated_at=now)
        ).rowcount
        db.commit()
        if not claimed:
            continue
        row = db.get(BroadcastSchedule, key)
        try:
            p = BroadcastCreate.model_validate(json.loads(row.payload_json))
            existing = db.scalar(select(Broadcast).where(Broadcast.idempotency_key == p.idempotency_key))
            if existing:
                # Dispatch may already have happened: report uncertainty, never repeat it.
                row.broadcast_id = existing.id
                row.status = "uncertain"
                row.error = "Публикация уже существует; повторная отправка запрещена"
                db.commit()
                continue
            if p.audience == "clubs":
                known = set(db.scalars(select(Club.id).where(Club.id.in_(p.club_ids))))
                owners = dict(db.execute(select(ClubSession.id, ClubSession.club_id).where(ClubSession.id.in_(p.session_ids))).all())
                if known != set(p.club_ids) or any(owners.get(sid) not in known for sid in p.session_ids):
                    raise ValueError("Аудитория изменилась: кружок или занятие удалены")
            b = Broadcast(
                title=p.title,
                body=p.body,
                url=p.url,
                audience=p.audience,
                club_ids=json.dumps(p.club_ids),
                session_ids=json.dumps(p.session_ids),
                author_id=row.author_id,
                author_login=row.author_login,
                idempotency_key=p.idempotency_key,
            )
            db.add(b)
            db.flush()
            row.broadcast_id = b.id
            db.commit()
            broadcast.dispatch(db, b)
            row.status = "sent"
            row.updated_at = now
            db.commit()
            audit.log("scheduled_broadcast_sent", broadcast_id=b.id, schedule_id=key)
        except Exception as exc:
            db.rollback()
            row = db.get(BroadcastSchedule, key)
            row.status = "uncertain" if row.broadcast_id else "failed"
            row.error = str(exc)[:500]
            row.updated_at = now
            db.commit()
