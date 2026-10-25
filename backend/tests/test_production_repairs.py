"""Regressions for the production audit, including optimized Python auth."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime

import pytest

from backend.app import settings
from backend.app.database import SessionLocal
from backend.app.models import Leader
from backend.app.models.attendance import Attendance, QrNonce, StudentDevice
from backend.app.routers import attendance as att
from backend.app.routers import public
from backend.app.services import client_logs
from backend.app.services.clock import MSK

from .test_attendance import MONDAY, SID, _checkin, _fixed_clock, _qr, set_clock  # noqa: F401
from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


@pytest.mark.parametrize("secret", ["", "short", " " * 40 + "short" + " " * 40])
def test_production_rejects_weak_file_secret(monkeypatch, tmp_path, secret):
    key = tmp_path / "secret.key"
    key.write_text(secret, encoding="utf-8")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET_FILE", str(key))
    monkeypatch.setenv("ALLOWED_HOSTS", "clubs.example.org")
    assert any("JWT_SECRET" in problem for problem in settings.validate_for_startup(tmp_path / "db.sqlite3"))
    assert key.read_text(encoding="utf-8") == secret
    key.write_text("s" * 48, encoding="utf-8")
    assert not settings.validate_for_startup(tmp_path / "db.sqlite3")


@pytest.mark.parametrize("prefix", ["itc-att1", "itc-att2", "itc-tx1", "tch1"])
def test_bare_credentials_redacted_in_every_log_field(prefix):
    token = f"{prefix}.payload.signature"
    entry = client_logs.normalize({"msg": token, "stack": token, "url": f"/qr?code={token}", "page": token}, {"device": token})
    assert token not in json.dumps(entry)
    assert "ordinary error" in client_logs.redact("ordinary error")


def test_closed_checkin_rolls_back_device_and_nonce_then_allows_retry(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    set_clock(hm="10:20")
    token = att.make_token(sid, MONDAY)[0]
    assert _checkin(admin_client, SID, sid, token, nonce="r" * 20).status_code == 403
    with SessionLocal() as db:
        assert db.get(StudentDevice, SID) is None
        assert db.get(QrNonce, "r" * 20) is None
    set_clock()
    assert _checkin(admin_client, SID, sid, _qr(admin_client, sid)["token"], nonce="r" * 20).status_code == 201
    assert _checkin(admin_client, SID, sid, _qr(admin_client, sid)["token"], nonce="s" * 20).status_code == 409
    with SessionLocal() as db:
        assert db.get(QrNonce, "s" * 20) is None
        assert db.query(Attendance).count() == 1


def test_moved_qr_actual_window_and_stable_original_identity(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    _post(
        admin_client,
        "/api/admin/exceptions/moves",
        {
            "session_id": sid,
            "original_date": MONDAY,
            "new_date": "2027-11-02",
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
        },
    )
    assert admin_client.post("/api/admin/attendance/qr", json={"session_id": sid, "date": MONDAY}).status_code == 409
    set_clock(day="2027-11-02", hm="12:02")
    qr = _qr(admin_client, sid, "2027-11-02")
    assert qr["state"] == "open" and qr["original_date"] == MONDAY
    assert _checkin(admin_client, SID, sid, qr["token"]).status_code == 201
    with SessionLocal() as db:
        assert db.query(Attendance).one().occurrence_date == MONDAY
    history = admin_client.get('/api/attendance/mine', headers={'X-Student-Id': SID, 'X-Device-Token': 'd' * 43}).json()
    assert history['items'][0]['date'] == '2027-11-02'
    assert history['items'][0]['start_time'] == '12:00'
    summary = admin_client.get('/api/admin/attendance/stats?date_from=2027-11-02&date_to=2027-11-02').json()
    assert summary['total'] == 1 and summary['occurrences'][0]['start_time'] == '12:00'
    choices = admin_client.get('/api/admin/attendance/occurrences?date=2027-11-02').json()
    assert choices[0]['original_date'] == MONDAY
    live = admin_client.get(f'/api/admin/attendance/live?session_id={sid}&date=2027-11-02&original_date={MONDAY}').json()
    assert live['count'] == 1 and len(live['ids']) == 1
    assert admin_client.delete(f"/api/admin/attendance/{live['ids'][0]}").status_code == 204
    live = admin_client.get(f'/api/admin/attendance/live?session_id={sid}&date=2027-11-02&original_date={MONDAY}').json()
    assert live['count'] == 0 and live['ids'] == []


def test_two_occurrences_same_actual_day_require_explicit_identity(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    _post(
        admin_client,
        "/api/admin/exceptions/moves",
        {
            "session_id": sid,
            "original_date": MONDAY,
            "new_date": "2027-11-08",
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
        },
    )
    set_clock(day="2027-11-08", hm="12:02")
    body = {"session_id": sid, "date": "2027-11-08"}
    assert admin_client.post("/api/admin/attendance/qr", json=body).status_code == 409
    qr = admin_client.post("/api/admin/attendance/qr", json={**body, "original_date": MONDAY}).json()
    assert qr["state"] == "open"
    assert _checkin(admin_client, SID, sid, qr["token"]).status_code == 201
    regular = admin_client.post("/api/admin/attendance/qr", json={**body, "original_date": "2027-11-08"}).json()
    assert regular["state"] == "closed"


def test_upcoming_changes_exclude_past_but_keep_incoming_move(admin_client, monkeypatch):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": sid, "original_date": MONDAY})
    _post(
        admin_client,
        "/api/admin/exceptions/moves",
        {
            "session_id": sid,
            "original_date": "2027-11-08",
            "new_date": "2027-11-16",
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
        },
    )
    monkeypatch.setattr(public, "now_msk", lambda: datetime(2027, 11, 10, tzinfo=MSK))
    changes = admin_client.get(f"/api/clubs/{w['club']['id']}").json()["upcoming_exceptions"]
    assert len(changes) == 1 and changes[0]["new_date"] == "2027-11-16"


def test_camera_policy_is_limited_to_qr_document(client):
    assert "camera=(self)" in client.get("/qr.html").headers["permissions-policy"]
    assert "camera=()" in client.get("/").headers["permissions-policy"]
    assert client.get("/api/attendance/mine").headers["cache-control"] == "no-store"


@pytest.mark.parametrize("query", ["weekday=0", "weekday=99", "category_id=-1", "room_id=0", "leader_id=-5"])
def test_invalid_public_filters_return_422(client, query):
    assert client.get(f"/api/schedule?week=2027-11-01&{query}").status_code == 422


@pytest.mark.parametrize('alias', ['20271101', '2027-W44-1', '2027-2-1', '9999-12-31'])
def test_canonical_attendance_dates_cannot_bypass_cancellation(admin_client, alias):
    w = make_world(admin_client)
    sid = w['session']['id']
    _post(admin_client, '/api/admin/exceptions/cancellations', {'session_id': sid, 'original_date': MONDAY})
    response = admin_client.post('/api/admin/attendance/manual', json={'session_id': sid, 'date': alias, 'student_id': SID})
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.query(Attendance).count() == 0

