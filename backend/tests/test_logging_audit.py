"""OPS-03: структурный журнал — неудачный вход и 500 оставляют запись с request_id, записи админа журналируются, секреты не попадают в лог."""
import json
import logging

from .helpers import PASSWORD, login, make_admin


def _audit(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "clubs.audit"]


def test_failed_login_is_audited_with_request_id_and_without_password(client, caplog):
    make_admin()
    caplog.set_level(logging.INFO)
    r = client.post("/api/admin/login", json={"login": "admin", "password": "wrong-password-1"}, headers={"X-Request-ID": "rid-fail-1"})
    assert r.status_code == 401
    records = _audit(caplog)
    assert any(x["event"] == "login_failed" and x["request_id"] == "rid-fail-1" and x["login"] == "admin" for x in records)
    assert "wrong-password-1" not in caplog.text


def test_admin_writes_are_audited_with_admin_id_and_no_body(client, caplog):
    make_admin()
    token = login(client).json()["access_token"]
    caplog.set_level(logging.INFO)
    r = client.post("/api/admin/categories", json={"name": "СекретноеИмя", "color": "#112233"}, headers={"Authorization": f"Bearer {token}", "X-Request-ID": "rid-w-1"})
    assert r.status_code == 201
    writes = [x for x in _audit(caplog) if x["event"] == "admin_write"]
    assert writes and writes[-1]["method"] == "POST" and writes[-1]["path"] == "/api/admin/categories"
    assert writes[-1]["request_id"] == "rid-w-1" and writes[-1]["admin_id"]
    assert "СекретноеИмя" not in caplog.text and PASSWORD not in caplog.text and token not in caplog.text
    client.get("/api/admin/categories", headers={"Authorization": f"Bearer {token}"})
    assert len([x for x in _audit(caplog) if x["event"] == "admin_write"]) == len(writes)  # чтения не журналируются


def test_unhandled_error_returns_500_with_request_id_and_is_logged(client, caplog, monkeypatch):
    from sqlalchemy.orm import Session

    def boom(self, *a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(Session, "scalars", boom)
    caplog.set_level(logging.INFO)
    r = client.get("/api/categories", headers={"X-Request-ID": "rid-500"})
    assert r.status_code == 500 and r.json()["request_id"] == "rid-500"
    assert "request_id=rid-500" in caplog.text and "kaboom" in caplog.text
