from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from ..models import BroadcastReceipt
from .broadcast import _utcnow


def mark(db, broadcast_id, install_id, channel, kind):
    now = _utcnow()
    key = hashlib.sha256(("broadcast-receipt|" + install_id).encode()).hexdigest()
    statement = insert(BroadcastReceipt).values(
        broadcast_id=broadcast_id, install_hash=key, channel=channel, shown_at=now, opened_at=now if kind == "opened" else None
    )
    statement = statement.on_conflict_do_update(
        index_elements=["broadcast_id", "install_hash", "channel"],
        set_={"opened_at": func.coalesce(BroadcastReceipt.opened_at, statement.excluded.opened_at)},
    )
    db.execute(statement)
    db.commit()


def counts(db, ids):
    return {
        row[0]: {"shown": row[1], "opened": row[2]}
        for row in db.execute(
            select(BroadcastReceipt.broadcast_id, func.count(), func.count(BroadcastReceipt.opened_at))
            .where(BroadcastReceipt.broadcast_id.in_(ids))
            .group_by(BroadcastReceipt.broadcast_id)
        )
    }


def deferred_result(db, payload, success):
    from sqlalchemy import update

    from ..models import Broadcast

    bid = payload.get("broadcast_id")
    if not isinstance(bid, int) or bid <= 0:
        return
    field = Broadcast.web_sent if success else Broadcast.web_failed
    db.execute(update(Broadcast).where(Broadcast.id == bid).values({field: field + 1}))
