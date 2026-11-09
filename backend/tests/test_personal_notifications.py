import json
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import NotificationTask, PushSubscription
from backend.app.schemas.push import ScheduleNotificationSettings
from backend.app.services import personal_notifications as pn
from backend.app.services import push
from backend.app.services.delivery import Event

from .test_push import ENDPOINT, sub_body


def now(s):
    return datetime.fromisoformat(s + "+03:00")


def sub(db, **settings):
    row = PushSubscription(
        endpoint=ENDPOINT, p256dh="key", auth="auth", club_id=None, announcements_only=False, schedule_settings=json.dumps(settings)
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    "time,a,b,expected",
    [
        ("2026-11-09T22:00", "22:00", "08:00", "2026-11-10T08:00"),
        ("2026-11-09T07:59", "22:00", "08:00", "2026-11-09T08:00"),
        ("2026-11-09T08:00", "22:00", "08:00", None),
        ("2026-11-09T13:00", "13:00", "15:00", "2026-11-09T15:00"),
        ("2026-11-09T15:00", "13:00", "15:00", None),
    ],
)
def test_quiet_boundaries(time, a, b, expected):
    s = ScheduleNotificationSettings(quiet_enabled=True, quiet_start=a, quiet_end=b)
    assert pn.quiet_until(s, now(time)) == (now(expected) if expected else None)


def test_opt_in_validation_settings_survive_new_club_sync(client):
    assert client.post("/api/push/schedule-settings/read", json={"endpoint": ENDPOINT}).status_code == 404
    client.post("/api/push/subscribe", json=sub_body())
    assert client.post("/api/push/schedule-settings/read", json={"endpoint": ENDPOINT}).json()["reminder_minutes"] == 0
    data = {
        "endpoint": ENDPOINT,
        "reminder_minutes": 17,
        "digest_enabled": True,
        "quiet_enabled": True,
        "quiet_start": "23:00",
        "quiet_end": "07:00",
    }
    assert client.post("/api/push/schedule-settings", json=data).status_code == 200
    client.post("/api/push/sync", json={**sub_body(), "club_ids": [], "announcements": True, "cancellations": True, "moves": True})
    assert client.post("/api/push/schedule-settings/read", json={"endpoint": ENDPOINT}).json()["reminder_minutes"] == 17
    assert client.post("/api/push/schedule-settings", json={**data, "quiet_end": "23:00"}).status_code == 422
    assert client.post("/api/push/schedule-settings", json={**data, "digest_time": "25:00"}).status_code == 422
    assert client.post("/api/push/schedule-settings", json={**data, "reminder_minutes": 121}).status_code == 422


def test_quiet_queue_unique_and_unsubscribe_drops_it(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "send_one", lambda *args: calls.append(args))
    with SessionLocal() as db:
        row = sub(db, quiet_enabled=True, quiet_start="22:00", quiet_end="08:00")
        ev = Event(kind="announcement", audience="all", club_ids=[], payload={"tag": "announcement:1", "title": "Update", "body": "Text"})
        assert pn.defer_if_quiet(db, row, ev, now("2026-11-09T23:00"))
        assert pn.defer_if_quiet(db, row, ev, now("2026-11-09T23:01"))
        assert len(list(db.scalars(select(NotificationTask)))) == 1
        assert pn.run(db, now("2026-11-10T07:59"))["sent"] == 0
        db.delete(row)
        db.commit()
        assert pn.run(db, now("2026-11-10T08:00"))["dropped"] == 1
        assert not calls


def event(status="scheduled", start="15:00"):
    return {
        "event_id": "1:2026-11-09",
        "club_id": 1,
        "date": "2026-11-09",
        "start_time": start,
        "end_time": "16:00",
        "club_name": "Robots",
        "room_name": "101",
        "status": status,
    }


def test_reminder_once_and_digest_once(monkeypatch):
    from backend.app.services import occurrence_source

    calls = []
    monkeypatch.setattr(push, "send_one", lambda _, p: calls.append(p))
    monkeypatch.setattr(occurrence_source, "load_snapshot", lambda _: None)
    monkeypatch.setattr(occurrence_source, "week_events", lambda *_: [event()])
    with SessionLocal() as db:
        sub(db, reminder_minutes=17, digest_enabled=True, digest_time="08:00")
        assert pn.run(db, now("2026-11-09T08:00"))["sent"] == 1
        assert pn.run(db, now("2026-11-09T08:01"))["sent"] == 0
        assert pn.run(db, now("2026-11-09T14:43"))["sent"] == 1
        assert pn.run(db, now("2026-11-09T14:44"))["sent"] == 0
        assert [p["kind"] for p in calls] == ["digest", "reminder"]


def test_cancelled_deferred_reminder_not_delivered(monkeypatch):
    from backend.app.services import occurrence_source

    current = [event()]
    calls = []
    monkeypatch.setattr(push, "send_one", lambda _, p: calls.append(p))
    monkeypatch.setattr(occurrence_source, "load_snapshot", lambda _: None)
    monkeypatch.setattr(occurrence_source, "week_events", lambda *_: current)
    with SessionLocal() as db:
        sub(db, reminder_minutes=30, quiet_enabled=True, quiet_start="14:00", quiet_end="14:50")
        assert pn.run(db, now("2026-11-09T14:30"))["sent"] == 0
        current[:] = [event(status="cancelled")]
        assert pn.run(db, now("2026-11-09T14:50"))["dropped"] == 1
        assert not calls


def test_quiet_past_class_start_does_not_queue_stale_reminder(monkeypatch):
    from backend.app.services import occurrence_source

    monkeypatch.setattr(occurrence_source, "load_snapshot", lambda _: None)
    monkeypatch.setattr(occurrence_source, "week_events", lambda *_: [event()])
    with SessionLocal() as db:
        sub(db, reminder_minutes=30, quiet_enabled=True, quiet_start="14:00", quiet_end="16:00")
        pn.run(db, now("2026-11-09T14:30"))
        assert not list(db.scalars(select(NotificationTask)))


def test_retry_lease_and_no_duplicate_after_success(monkeypatch):
    calls = []

    def transport(_, payload):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("temporary")

    monkeypatch.setattr(push, "send_one", transport)
    with SessionLocal() as db:
        row = sub(db, quiet_enabled=True, quiet_start="22:00", quiet_end="08:00")
        ev = Event(kind="announcement", audience="all", club_ids=[], payload={"tag": "retry", "title": "Update"})
        pn.defer_if_quiet(db, row, ev, now("2026-11-09T23:00"))
        assert pn.run(db, now("2026-11-10T08:00"))["sent"] == 0
        task = db.scalar(select(NotificationTask))
        assert task.attempts == 1
        assert pn.run(db, now("2026-11-10T08:02"))["sent"] == 1
        assert pn.run(db, now("2026-11-10T08:03"))["sent"] == 0
        assert len(calls) == 2


def test_changed_preferences_revoke_queued_reminder(monkeypatch):
    from backend.app.services import occurrence_source

    monkeypatch.setattr(occurrence_source, "load_snapshot", lambda _: None)
    monkeypatch.setattr(occurrence_source, "week_events", lambda *_: [event()])
    calls = []
    monkeypatch.setattr(push, "send_one", lambda *args: calls.append(args))
    with SessionLocal() as db:
        row = sub(db, reminder_minutes=30, quiet_enabled=True, quiet_start="14:00", quiet_end="14:50")
        pn.run(db, now("2026-11-09T14:30"))
        row.schedule_settings = "{}"
        db.commit()
        assert pn.run(db, now("2026-11-09T14:50"))["dropped"] == 1
        assert not calls


def test_changed_minutes_replace_unsent_but_not_sent_reminder(monkeypatch):
    from backend.app.services import occurrence_source

    monkeypatch.setattr(occurrence_source, "load_snapshot", lambda _: None)
    monkeypatch.setattr(occurrence_source, "week_events", lambda *_: [event()])
    calls = []
    monkeypatch.setattr(push, "send_one", lambda _, payload: calls.append(payload))
    with SessionLocal() as db:
        row = sub(db, reminder_minutes=30, quiet_enabled=True, quiet_start="14:00", quiet_end="14:50")
        pn.run(db, now("2026-11-09T14:30"))
        row.schedule_settings = json.dumps({"reminder_minutes": 17})
        db.commit()
        assert pn.run(db, now("2026-11-09T14:43"))["sent"] == 1
        row.schedule_settings = json.dumps({"reminder_minutes": 10})
        db.commit()
        assert pn.run(db, now("2026-11-09T14:50"))["sent"] == 0
        assert len(calls) == 1 and calls[0]["reminder_minutes"] == 17
