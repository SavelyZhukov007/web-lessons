"""Phase 2 F: /api/app/info (опознание сервера приложением), CORS для origin приложения, журнал ошибок клиентов."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import settings
from backend.app.main import app
from backend.app.services import client_logs, mdns

from .test_exception_conflicts_api import admin_client  # noqa: F401


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def logs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_LOGS_DIR", str(tmp_path / "logs"))
    client_logs.reset_limits()
    yield tmp_path / "logs"
    client_logs.reset_limits()


def test_app_info(client, monkeypatch):
    monkeypatch.setenv("SERVER_NAME", "Тестовый стенд")
    r = client.get("/api/app/info")
    j = r.json()
    assert r.status_code == 200 and j["app"] == "itc-kruzhki" and j["name"] == "Тестовый стенд"
    assert j["api_version"] == 1 and j["version"] and len(j["server_id"]) == 16
    assert client.get("/api/app/info").json()["server_id"] == j["server_id"]  # стабильный


@pytest.mark.parametrize("origin", ["http://localhost", "https://localhost", "capacitor://localhost"])
def test_cors_app_origins(client, origin):
    r = client.options("/api/app/info", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == origin
    assert client.get("/api/app/info", headers={"Origin": origin}).headers.get("access-control-allow-origin") == origin


def test_cors_foreign_origin_denied(client):
    assert "access-control-allow-origin" not in client.get("/api/app/info", headers={"Origin": "https://evil.example"}).headers


def test_cors_settings(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example/")
    assert settings.cors_origins()[0] == "https://a.example" and "capacitor://localhost" in settings.cors_origins()
    monkeypatch.setenv("CORS_APP_ORIGINS", "0")
    assert settings.cors_origins() == ["https://a.example"]


def _batch(n=2, **kw):
    return {"device": "dev-1234567890", "version": "1.2", "platform": "android", "os": "Android 14", "webview": "Chrome 124",
            "entries": [{"t": 1793000000000 + i, "level": "error", "kind": "js", "msg": f"Ошибка {i}", "stack": "at a.js:1"} for i in range(n)], **kw}


def test_post_logs_and_admin_view(client, admin_client):
    assert client.post("/api/logs", json=_batch(3)).json() == {"accepted": 3}
    secret = {"t": 1793000001000, "level": "warn", "kind": "http", "msg": 'fetch /api/admin/login {"password":"hunter2"} Authorization: Bearer abc.def.ghijklmnop token=XYZ123 eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlMTIz',
              "status": 500, "url": "/api/admin/login"}
    client.post("/api/logs", json={**_batch(0), "entries": [secret, {"level": "info", "msg": "nav"}, "мусор"]})
    j = admin_client.get("/api/admin/logs").json()
    assert len(j["items"]) == 5 and j["versions"] == ["1.2"]
    msgs = " ".join(e["msg"] for e in j["items"])
    for leak in ("hunter2", "abc.def", "XYZ123", "eyJhbGci"):
        assert leak not in msgs
    assert len(admin_client.get("/api/admin/logs?level=warn").json()["items"]) == 4
    assert admin_client.get("/api/admin/logs?version=9.9").json()["items"] == []
    assert len(admin_client.get("/api/admin/logs?device=dev-12").json()["items"]) == 5
    txt = admin_client.get("/api/admin/logs.txt?level=error")
    assert txt.status_code == 200 and "attachment" in txt.headers["content-disposition"]
    assert txt.text.count("ERROR") == 3 and "Ошибка 0" in txt.text and "    at a.js:1" in txt.text


def test_logs_admin_only(client):
    assert client.get("/api/admin/logs").status_code == 401
    assert client.get("/api/admin/logs.txt").status_code == 401


def test_logs_limits(client, monkeypatch):
    assert client.post("/api/logs", content=b"x" * (client_logs.MAX_BODY + 1), headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/api/logs", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/logs", json={"entries": "x"}).status_code == 422
    big = client.post("/api/logs", json={**_batch(0), "entries": [{"msg": "y" * 100}] * 600}).json()
    assert big["accepted"] == client_logs.MAX_ENTRIES
    monkeypatch.setattr(client_logs, "RATE", 3)
    client_logs.reset_limits()
    codes = [client.post("/api/logs", json=_batch(1)).status_code for _ in range(5)]
    assert codes[:3] == [202, 202, 202] and codes[3:] == [429, 429]


def test_logs_retention(logs_dir, monkeypatch):
    monkeypatch.setenv("LOGS_RETENTION_DAYS", "7")
    logs_dir.mkdir(parents=True)
    today = date(2026, 10, 24)
    for d in (0, 6, 8, 30):
        (logs_dir / f"client-{(today - timedelta(days=d)).isoformat()}.jsonl").write_text("{}\n", encoding="utf-8")
    (logs_dir / "client-garbage.jsonl").write_text("", encoding="utf-8")
    assert client_logs.cleanup(today) == 2
    assert sorted(p.name for p in logs_dir.iterdir()) == ["client-2026-10-18.jsonl", "client-2026-10-24.jsonl", "client-garbage.jsonl"]


def test_mdns_service_info():
    pytest.importorskip("zeroconf")
    info = mdns.service_info(port=8123, ip="192.168.1.50")
    assert info.type == "_itc-kruzhki._tcp.local." and info.port == 8123
    assert info.properties[b"app"] == b"itc-kruzhki"


def test_mdns_without_package(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(ImportError()) if n == "zeroconf" else real(n, *a, **k))
    assert mdns.start() is None
    mdns.stop(None)
