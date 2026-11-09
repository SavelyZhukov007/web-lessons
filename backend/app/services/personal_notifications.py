"""Opt-in Moscow-time web reminders/digests and persistent quiet-hour delivery.
No endpoint/token is copied into the queue; unsubscribe is checked at dispatch.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert

from ..models.notification_task import NotificationTask
from ..models.push_subscription import PushSubscription
from ..schemas.push import ScheduleNotificationSettings

MSK = ZoneInfo("Europe/Moscow")
log = logging.getLogger("clubs.personal_notifications")


def read_settings(row):
    try:
        return ScheduleNotificationSettings.model_validate_json(row.schedule_settings or "{}")
    except (ValueError, TypeError):
        return ScheduleNotificationSettings()


def target_key(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()


def quiet_until(settings, now):
    now = now.astimezone(MSK)
    if not settings.quiet_enabled:
        return None
    minute = now.hour * 60 + now.minute
    a, b = [int(v[:2]) * 60 + int(v[3:]) for v in (settings.quiet_start, settings.quiet_end)]
    quiet = a <= minute < b if a < b else minute >= a or minute < b
    if not quiet:
        return None
    end = now.replace(hour=b // 60, minute=b % 60, second=0, microsecond=0)
    if end <= now:
        end += timedelta(days=1)
    return end


def utc_naive(t):
    return t.astimezone(timezone.utc).replace(tzinfo=None)


def enqueue(db, sub, payload, kind, due, expires, suffix=""):
    target = target_key(sub.endpoint)
    key = hashlib.sha256((target + "|" + str(payload.get("tag")) + "|" + suffix).encode()).hexdigest()
    encoded = json.dumps(payload, ensure_ascii=False)
    statement = insert(NotificationTask).values(
        key=key, target=target, payload=encoded, kind=kind, due=utc_naive(due), expires=utc_naive(expires), status="pending", attempts=0
    )
    # A changed N/occurrence can replace an unsent reminder, never one already delivered.
    statement = statement.on_conflict_do_update(
        index_elements=[NotificationTask.key],
        set_={"payload": encoded, "due": utc_naive(due), "expires": utc_naive(expires), "status": "pending", "attempts": 0},
        where=(NotificationTask.kind == "reminder")
        & (statement.excluded.kind == "reminder")
        & NotificationTask.status.in_(["pending", "dropped"])
        & (NotificationTask.payload != encoded),
    )
    db.execute(statement)
    db.commit()


def defer_if_quiet(db, sub, ev, now=None):
    now = now or datetime.now(timezone.utc)
    due = quiet_until(read_settings(sub), now)
    if due is None:
        return False
    enqueue(db, sub, ev.payload, ev.kind, due, now + timedelta(hours=48))
    return True


def allowed(rows, task, payload):
    if not rows:
        return False
    settings = read_settings(rows[0])
    if task.kind == "reminder" and settings.reminder_minutes <= 0:
        return False
    if task.kind == "digest" and not settings.digest_enabled:
        return False
    flag = {"announcement": "announcements", "cancel": "cancellations", "reschedule": "moves"}.get(task.kind)
    candidates = [r for r in rows if not flag or getattr(r, flag)]
    club = payload.get("club_id")
    if task.kind in {"reminder", "cancel", "reschedule"}:
        return any(not r.announcements_only and (r.club_id is None or r.club_id == club) for r in candidates)
    return bool(candidates)


def run(db, now=None):
    from . import occurrence_source as source
    from . import push

    now = now or datetime.now(timezone.utc)
    local = now.astimezone(MSK)
    naive = utc_naive(now)
    # Reclaim only expired worker leases; a live send has a 10-second transport timeout.
    db.execute(
        update(NotificationTask)
        .where(NotificationTask.status == "claimed", NotificationTask.due <= naive, NotificationTask.attempts < 3)
        .values(status="pending")
    )
    db.commit()
    grouped = {}
    for row in db.scalars(select(PushSubscription).order_by(PushSubscription.id)):
        grouped.setdefault(target_key(row.endpoint), []).append(row)
    active = [rows for rows in grouped.values() if (s := read_settings(rows[0])).reminder_minutes or s.digest_enabled]
    if active:
        week = local.date() - timedelta(days=local.weekday())
        events = source.week_events(source.load_snapshot(db), week)
        today = [e for e in events if e["date"] == local.date().isoformat() and e["status"] != "cancelled"]
        for rows in active:
            sub = rows[0]
            settings = read_settings(sub)
            mine = [e for e in today if any(not r.announcements_only and (r.club_id is None or r.club_id == e["club_id"]) for r in rows)]
            for e in mine:
                start = datetime.fromisoformat(e["date"] + "T" + e["start_time"]).replace(tzinfo=MSK)
                at = start - timedelta(minutes=settings.reminder_minutes)
                if settings.reminder_minutes and at <= now < min(start, at + timedelta(minutes=10)):
                    due = quiet_until(settings, now) or now
                    if due >= start:
                        continue
                    enqueue(
                        db,
                        sub,
                        {
                            "title": e["club_name"],
                            "body": e["start_time"] + "–" + e["end_time"] + " · " + e["room_name"],
                            "url": "/?day=" + e["date"] + "&event=" + e["event_id"],
                            "tag": "reminder:" + e["event_id"] + ":" + e["start_time"],
                            "club_id": e["club_id"],
                            "kind": "reminder",
                            "badge": False,
                            "event_id": e["event_id"],
                            "date": e["date"],
                            "start_time": e["start_time"],
                            "reminder_minutes": settings.reminder_minutes,
                        },
                        "reminder",
                        due,
                        start,
                    )
            at = local.replace(hour=int(settings.digest_time[:2]), minute=int(settings.digest_time[3:]), second=0, microsecond=0)
            if settings.digest_enabled and mine and at <= now < at + timedelta(minutes=15):
                due = quiet_until(settings, now) or now
                body = " · ".join(e["start_time"] + " " + e["club_name"] for e in mine)[:450]
                enqueue(
                    db,
                    sub,
                    {
                        "title": "Сегодня в «Моих кружках»: " + str(len(mine)),
                        "body": body,
                        "url": "/?my=1&day=" + local.date().isoformat(),
                        "tag": "digest:" + local.date().isoformat(),
                        "kind": "digest",
                        "badge": False,
                    },
                    "digest",
                    due,
                    local.replace(hour=23, minute=59, second=59),
                )
    result = {"sent": 0, "failed": 0, "dropped": 0}
    tasks = list(
        db.scalars(
            select(NotificationTask)
            .where(NotificationTask.status == "pending", NotificationTask.due <= naive)
            .order_by(NotificationTask.due)
            .limit(200)
        )
    )
    for task in tasks:
        old_rows = grouped.get(task.target, [])
        rows = (
            list(
                db.scalars(
                    select(PushSubscription)
                    .where(PushSubscription.endpoint == old_rows[0].endpoint)
                    .execution_options(populate_existing=True)
                )
            )
            if old_rows
            else []
        )
        payload = json.loads(task.payload)
        if rows and task.kind in {"reminder", "digest"}:
            current = source.week_events(source.load_snapshot(db), local.date() - timedelta(days=local.weekday()))
            mine = [
                e
                for e in current
                if e["date"] == local.date().isoformat()
                and e["status"] != "cancelled"
                and any(not r.announcements_only and (r.club_id is None or r.club_id == e["club_id"]) for r in rows)
            ]
            if task.kind == "reminder":
                valid = any(
                    e["event_id"] == payload.get("event_id")
                    and e["date"] == payload.get("date")
                    and e["start_time"] == payload.get("start_time")
                    for e in mine
                ) and read_settings(rows[0]).reminder_minutes == payload.get("reminder_minutes")
                if valid:
                    current_event = next(e for e in mine if e["event_id"] == payload["event_id"])
                    payload["title"] = current_event["club_name"]
                    payload["body"] = current_event["start_time"] + "–" + current_event["end_time"] + " · " + current_event["room_name"]
            else:
                mine = [e for e in mine if datetime.fromisoformat(e["date"] + "T" + e["end_time"]).replace(tzinfo=MSK) > now]
                valid = bool(mine)
                payload["title"] = "Сегодня в «Моих кружках»: " + str(len(mine))
                payload["body"] = " · ".join(e["start_time"] + " " + e["club_name"] for e in mine)[:450]
            if not valid:
                task.status = "dropped"
                result["dropped"] += 1
                db.commit()
                continue
        if task.kind in {"cancel", "reschedule"} and str(payload.get("tag", "")).startswith("exception-"):
            from ..models.session_exception import SessionException

            try:
                exception = db.get(SessionException, int(payload["tag"].removeprefix("exception-")))
            except ValueError:
                exception = None
            if exception is None or exception.type != ("cancelled" if task.kind == "cancel" else "moved"):
                task.status = "dropped"
                result["dropped"] += 1
                db.commit()
                continue
        if task.expires <= naive or not allowed(rows, task, payload):
            task.status = "dropped"
            result["dropped"] += 1
            db.commit()
            continue
        end = quiet_until(read_settings(rows[0]), now)
        if end:
            task.due = utc_naive(end)
            db.commit()
            continue
        # Atomic claim survives multiple ASGI workers. Stable tag deduplicates uncertain transport retries.
        claimed = db.execute(
            update(NotificationTask)
            .where(NotificationTask.key == task.key, NotificationTask.status == "pending")
            .values(status="claimed", attempts=NotificationTask.attempts + 1, due=naive + timedelta(minutes=2))
        ).rowcount
        db.commit()
        if not claimed:
            continue
        sub = rows[0]
        try:
            push.send_one({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, payload)
            task.status = "sent"
            result["sent"] += 1
        except push.PushGone:
            db.execute(delete(PushSubscription).where(PushSubscription.endpoint == sub.endpoint))
            task.status = "dropped"
            result["dropped"] += 1
        except Exception:
            task.status = "pending" if task.attempts < 3 else "failed"
            task.due = naive + timedelta(minutes=2)
            result["failed"] += 1
            log.warning("scheduled notification transport failure")
        db.commit()
    db.execute(delete(NotificationTask).where(NotificationTask.expires < naive - timedelta(days=7)))
    db.commit()
    return result
