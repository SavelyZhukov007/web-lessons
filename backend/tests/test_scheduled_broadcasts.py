from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import Broadcast, BroadcastReceipt, BroadcastSchedule
from backend.app.services import scheduled_broadcasts
from backend.app.services.broadcast import _utcnow

from .test_broadcasts import msg, sent  # noqa: F401
from .test_exception_conflicts_api import admin_client, make_world  # noqa: F401


def schedule(client, **extra):
    when = (_utcnow() + timedelta(minutes=2)).replace(tzinfo=timezone.utc).isoformat()
    result = client.post("/api/admin/broadcasts", json=msg(scheduled_at=when, **extra))
    assert result.status_code == 201, result.text
    return result.json()


def test_schedule_is_not_in_feed_until_publication_and_never_skips_legacy_cursor(admin_client, sent):
    planned = schedule(admin_client)
    assert planned["status"] == "scheduled" and not sent
    first = admin_client.get("/api/announcements").json()
    assert first == {"items": [], "last_id": 0}
    immediate = admin_client.post("/api/admin/broadcasts", json=msg(key="second-immediate", title="Сразу")).json()
    seen = immediate["id"]
    with SessionLocal() as db:
        scheduled_broadcasts.run(db, _utcnow() + timedelta(minutes=3))
        scheduled_broadcasts.run(db, _utcnow() + timedelta(minutes=4))
        row = db.get(BroadcastSchedule, planned["schedule_id"])
        assert row.status == "sent" and row.broadcast_id > seen
    feed = admin_client.get("/api/announcements", params={"since": seen}).json()
    assert len(feed["items"]) == 1 and feed["items"][0]["id"] > seen
    assert feed["last_id"] == feed["items"][0]["id"]


def test_schedule_idempotency_and_cancel_before_claim(admin_client, sent):
    planned = schedule(admin_client)
    again = admin_client.post("/api/admin/broadcasts", json=msg()).json()
    assert again["duplicate"] and again["schedule_id"] == planned["schedule_id"]
    assert admin_client.delete("/api/admin/broadcasts/schedules/" + planned["schedule_id"]).status_code == 200
    assert admin_client.delete("/api/admin/broadcasts/schedules/" + planned["schedule_id"]).status_code == 409
    with SessionLocal() as db:
        scheduled_broadcasts.run(db, _utcnow() + timedelta(minutes=4))
        assert not list(db.scalars(select(Broadcast)))
    assert not sent


def test_interrupted_send_is_never_repeated_automatically(admin_client, sent):
    planned = schedule(admin_client)
    with SessionLocal() as db:
        row = db.get(BroadcastSchedule, planned["schedule_id"])
        row.status = "sending"
        row.updated_at = _utcnow() - timedelta(minutes=10)
        db.commit()
        scheduled_broadcasts.run(db)
        assert row.status == "uncertain"
        assert not list(db.scalars(select(Broadcast)))
    assert not sent


def test_missing_audience_fails_without_widening_consent(admin_client, sent):
    world = make_world(admin_client)
    planned = schedule(admin_client, audience="clubs", club_ids=[world["club"]["id"]])
    admin_client.delete("/api/admin/sessions/" + str(world["session"]["id"]))
    admin_client.delete("/api/admin/clubs/" + str(world["club"]["id"]))
    with SessionLocal() as db:
        scheduled_broadcasts.run(db, _utcnow() + timedelta(minutes=3))
        assert db.get(BroadcastSchedule, planned["schedule_id"]).status == "failed"
        assert not list(db.scalars(select(Broadcast)))
    assert not sent


def test_schedule_requires_aware_future_timestamp(admin_client):
    for value in ["2026-11-09T20:00:00", "2020-01-01T00:00:00Z", (_utcnow() + timedelta(days=370)).isoformat() + "Z"]:
        assert admin_client.post("/api/admin/broadcasts", json=msg(scheduled_at=value)).status_code == 422


def test_receipts_are_anonymous_and_deduplicated(admin_client, sent):
    b = admin_client.post("/api/admin/broadcasts", json=msg()).json()
    url = "/api/announcements/" + str(b["id"]) + "/receipt"
    body = {"install_id": "anonymous-install-001", "channel": "web", "kind": "shown"}
    for kind in ["shown", "shown", "opened", "opened"]:
        assert admin_client.post(url, json={**body, "kind": kind}).status_code == 204
    item = admin_client.get("/api/admin/broadcasts").json()["items"][0]
    assert item["shown"] == item["opened"] == 1
    with SessionLocal() as db:
        rows = list(db.scalars(select(BroadcastReceipt)))
        assert len(rows) == 1 and rows[0].install_hash != body["install_id"]
        assert body["install_id"] not in rows[0].install_hash
    assert admin_client.post("/api/announcements/99999/receipt", json=body).status_code == 404


def test_pending_schedule_is_an_undo_dependency(admin_client):
    world = make_world(admin_client)
    action = next(x for x in admin_client.get("/api/admin/actions").json()["items"] if x.get("path") == "/api/admin/sessions")
    schedule(admin_client, audience="clubs", club_ids=[world["club"]["id"]], session_ids=[world["session"]["id"]])
    result = admin_client.post("/api/admin/actions/" + str(action["id"]) + "/undo")
    assert result.status_code == 409 and "рассылка" in result.text
