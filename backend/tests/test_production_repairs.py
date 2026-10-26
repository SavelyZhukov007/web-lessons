"""Regressions for the production audit, including optimized Python auth."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.app import settings
from backend.app.routers import public
from backend.app.services import client_logs
from backend.app.services.clock import MSK

MONDAY = "2027-11-01"
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


def test_ordinary_log_text_is_kept():
    assert "ordinary error" in client_logs.redact("ordinary error")


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


def test_camera_is_disabled_everywhere(client):
    assert "camera=()" in client.get("/").headers["permissions-policy"]
    assert client.get("/qr.html").status_code == 404


@pytest.mark.parametrize("query", ["weekday=0", "weekday=99", "category_id=-1", "room_id=0", "leader_id=-5"])
def test_invalid_public_filters_return_422(client, query):
    assert client.get(f"/api/schedule?week=2027-11-01&{query}").status_code == 422


