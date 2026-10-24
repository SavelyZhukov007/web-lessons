"""Refresh-токены с ротацией: короткий access, одноразовый refresh, обнаружение повторного использования."""
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from backend.app import settings
from backend.app.database import SessionLocal
from backend.app.models import AdminSession

from .helpers import login, make_admin


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _refresh(client, token=None, **kw):
    return client.post("/api/admin/refresh", json={"refresh_token": token} if token else None, **kw)


def test_access_token_is_short_lived_and_refresh_token_is_not_stored_in_clear(client):
    make_admin()
    body = login(client).json()
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        secret = body["refresh_token"].split(".", 1)[1]
        assert secret not in (row.refresh_hash or "") and len(row.refresh_hash) == 64


def test_refresh_rotates_pair_and_old_refresh_is_dead(client):
    make_admin()
    first = login(client).json()
    client.cookies.clear()
    second = _refresh(client, first["refresh_token"])
    assert second.status_code == 200, second.text
    b = second.json()
    assert b["refresh_token"] != first["refresh_token"] and b["access_token"] != first["access_token"]
    assert client.get("/api/admin/status", headers=_bearer(b["access_token"])).status_code == 200
    # access, выданный до ротации, больше не действует (jti сменился)
    assert client.get("/api/admin/status", headers=_bearer(first["access_token"])).status_code == 401
    # новый refresh работает, цепочка продолжается
    third = _refresh(client, b["refresh_token"])
    assert third.status_code == 200 and third.json()["refresh_token"] != b["refresh_token"]


def test_reuse_of_rotated_token_inside_grace_is_409_and_session_survives(client):
    make_admin()
    first = login(client).json()
    client.cookies.clear()
    new = _refresh(client, first["refresh_token"]).json()
    again = _refresh(client, first["refresh_token"])
    assert again.status_code == 409
    assert _refresh(client, new["refresh_token"]).status_code == 200  # сессия цела


def test_reuse_after_grace_revokes_whole_session(client, monkeypatch):
    make_admin()
    first = login(client).json()
    client.cookies.clear()
    new = _refresh(client, first["refresh_token"]).json()
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        row.refresh_rotated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=settings.refresh_grace_seconds() + 5)
        db.commit()
    assert _refresh(client, first["refresh_token"]).status_code == 401  # старый токен предъявлен позже — кража
    with SessionLocal() as db:
        assert db.scalar(select(AdminSession)) is None
    assert _refresh(client, new["refresh_token"]).status_code == 401  # легитимный тоже мёртв: нужен новый вход
    assert client.get("/api/admin/status", headers=_bearer(new["access_token"])).status_code == 401


def test_refresh_via_cookie_and_cookie_flags(client):
    make_admin()
    r = login(client)
    cookies = r.headers.get_list("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith("admin_refresh="))
    assert "HttpOnly" in refresh_cookie and "Path=/api/admin/refresh" in refresh_cookie and "SameSite=strict" in refresh_cookie
    r2 = client.post("/api/admin/refresh")  # токен только в cookie
    assert r2.status_code == 200
    assert client.get("/api/admin/status").status_code == 200  # новый access-cookie принят


def test_refresh_rejects_garbage_missing_and_unknown(client):
    make_admin()
    assert client.post("/api/admin/refresh").status_code == 401
    for bad in ("x", "1.", ".abc", "abc.def", "999999.secret-secret", "1." + "a" * 50):
        assert _refresh(client, bad).status_code in (401, 422), bad


def test_expired_session_cannot_refresh(client):
    make_admin()
    first = login(client).json()
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert _refresh(client, first["refresh_token"]).status_code == 401


def test_refresh_extends_sliding_expiry_and_logout_kills_refresh(client):
    make_admin()
    first = login(client).json()
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        db.commit()
    new = _refresh(client, first["refresh_token"]).json()
    with SessionLocal() as db:
        assert db.scalar(select(AdminSession)).expires_at > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=6)
    assert client.post("/api/admin/logout", headers=_bearer(new["access_token"])).status_code == 204
    assert _refresh(client, new["refresh_token"]).status_code == 401


def test_password_change_kills_other_sessions_refresh_tokens(client):
    make_admin()
    other = login(client).json()
    mine = login(client).json()
    r = client.post("/api/admin/password", json={"current_password": "Password123", "new_password": "N3w-Passw0rd-xyz"}, headers=_bearer(mine["access_token"]))
    assert r.status_code == 204
    assert _refresh(client, other["refresh_token"]).status_code == 401
    assert _refresh(client, mine["refresh_token"]).status_code == 200


def test_refresh_event_is_audited_without_token(client, caplog):
    import logging

    make_admin()
    first = login(client).json()
    caplog.set_level(logging.INFO)
    _refresh(client, first["refresh_token"])
    assert "token_refreshed" in caplog.text and first["refresh_token"] not in caplog.text
