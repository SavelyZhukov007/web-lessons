"""Счётчик пользователей: ping (обезличенно, без нагрузочного теста, лимит), сводка /api/admin/stats, забывание через 60 дней."""
from __future__ import annotations

from datetime import timedelta

from backend.app.database import SessionLocal
from backend.app.models import AppDevice, Install
from backend.app.services import broadcast as broadcast_service
from backend.app.services import client_logs
from backend.app.services import stats as service

from .test_exception_conflicts_api import admin_client  # noqa: F401

ID = "a" * 32


def test_ping_stores_only_hash_and_kind(client):
    client_logs.reset_limits()
    assert client.post("/api/app/ping", json={"install_id": ID, "kind": "ios-pwa"}).status_code == 204
    with SessionLocal() as db:
        rows = db.query(Install).all()
        assert len(rows) == 1 and rows[0].id_hash == service.install_key(ID) and ID not in rows[0].id_hash
        assert rows[0].kind == "ios-pwa"
        assert {c.name for c in Install.__table__.columns} == {"id_hash", "kind", "first_seen", "last_seen"}


def test_ping_validation_stress_and_rate_limit(client):
    client_logs.reset_limits()
    assert client.post("/api/app/ping", json={"install_id": "short", "kind": "web"}).status_code == 422
    assert client.post("/api/app/ping", json={"install_id": ID, "kind": "evil"}).status_code == 422
    r = client.post("/api/app/ping", json={"install_id": ID}, headers={"User-Agent": "KipClub-stress/1.0 (guest, read-only)"})
    assert r.status_code == 204
    with SessionLocal() as db:
        assert db.query(Install).count() == 0
    codes = [client.post("/api/app/ping", json={"install_id": ID}).status_code for _ in range(client_logs.RATE + 1)]
    assert codes[-1] == 429 and codes[0] == 204
    client_logs.reset_limits()


def test_stats_summary_and_forget(admin_client):  # noqa: F811
    client_logs.reset_limits()
    assert admin_client.get("/api/admin/stats").status_code == 200
    now = service._utcnow()
    with SessionLocal() as db:
        db.add_all([
            Install(id_hash="w1", kind="web", first_seen=now, last_seen=now),
            Install(id_hash="i1", kind="ios-pwa", first_seen=now - timedelta(days=20), last_seen=now - timedelta(days=3)),
            Install(id_hash="old", kind="web", first_seen=now - timedelta(days=90), last_seen=now - timedelta(days=61)),
            AppDevice(id_hash="d1", club_ids="[]", platform="android", app_version="v0.7.016", fcm_token="tok", last_seen=now),
        ])
        db.commit()
    s = admin_client.get("/api/admin/stats").json()
    assert s["total"] == 3 and s["by_kind"] == {"android-apk": 1, "ios-pwa": 1, "web": 1}
    assert s["active"]["day"]["total"] == 2 and s["active"]["week"]["ios-pwa"] == 1 and s["active"]["month"]["total"] == 3
    assert s["new_week"] == 1 and s["push"] == {"web": 0, "fcm": 1} and s["admins"] == 1
    # новая установка чистит забытые (>60 дней)
    assert admin_client.post("/api/app/ping", json={"install_id": "b" * 32}).status_code == 204
    with SessionLocal() as db:
        assert db.get(Install, "old") is None
    assert broadcast_service.DEVICE_FORGET_DAYS == 60


def test_stats_requires_admin(client):
    assert client.get("/api/admin/stats").status_code == 401
