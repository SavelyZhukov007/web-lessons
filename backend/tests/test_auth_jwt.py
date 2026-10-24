import base64
import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from backend.app import auth, settings
from backend.app.database import SessionLocal
from backend.app.models import AdminSession, LoginAttempt
from backend.app.services import login_limiter
from backend.app.services.tokens import ALGORITHM

from .helpers import PASSWORD, login, make_admin


def test_login_returns_jwt_cookie_and_bearer_token(client):
    make_admin()
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60 and body["refresh_expires_in"] == 7 * 24 * 3600 and body["refresh_token"]
    claims = jwt.decode(body["access_token"], settings.jwt_secret(), algorithms=[ALGORITHM], issuer="clubs-schedule")
    assert claims["sub"] == str(body["admin"]["id"])
    assert {"sid", "jti", "iat", "exp"} <= claims.keys()
    # cookie содержит тот же JWT и HttpOnly/SameSite
    cookie = r.headers["set-cookie"]
    assert body["access_token"] in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    # в БД лежит хэш jti, а не сам токен/jti
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        assert row.token_hash == auth.hash_session_token(claims["jti"])
        assert claims["jti"] not in row.token_hash


def test_bearer_header_authenticates_without_cookie(client):
    make_admin()
    token = login(client).json()["access_token"]
    client.cookies.clear()
    assert client.get("/api/admin/status").status_code == 401
    r = client.get("/api/admin/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["admin"]["login"] == "admin"


def test_logout_revokes_token_even_if_jwt_still_valid(client):
    make_admin()
    token = login(client).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/admin/logout", headers=h).status_code == 204
    assert client.get("/api/admin/status", headers=h).status_code == 401


def _forge(claims, secret=None, alg="HS256"):
    return jwt.encode(claims, secret or settings.jwt_secret(), algorithm=alg)


def test_tampered_expired_and_foreign_tokens_rejected(client):
    make_admin()
    good = login(client).json()["access_token"]
    claims = jwt.decode(good, options={"verify_signature": False})
    client.cookies.clear()

    def status(token):
        return client.get("/api/admin/status", headers={"Authorization": f"Bearer {token}"}).status_code

    assert status(good) == 200
    assert status(_forge(claims, secret="wrong-secret-" + "y" * 40)) == 401  # чужая подпись
    assert status(_forge({**claims, "exp": int(time.time()) - 10})) == 401  # просрочен
    assert status(_forge({**claims, "iss": "evil"})) == 401
    assert status(_forge({**claims, "sub": "999"})) == 401  # sub не совпадает с владельцем сессии
    assert status(_forge({**claims, "jti": "other"})) == 401  # jti не соответствует хэшу в БД
    # alg=none
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    assert status((header + b"." + payload + b".").decode()) == 401
    assert status("not-a-jwt") == 401


def test_expired_server_session_is_401_and_deleted(client):
    make_admin()
    token = login(client).json()["access_token"]
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    r = client.get("/api/admin/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(AdminSession)) is None


def test_login_cleans_expired_sessions(client):
    make_admin()
    login(client)
    with SessionLocal() as db:
        row = db.scalar(select(AdminSession))
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        db.commit()
    login(client)
    with SessionLocal() as db:
        assert len(list(db.scalars(select(AdminSession)))) == 1


def test_cookie_secure_flag_in_production(client, monkeypatch):
    make_admin()
    assert "Secure" not in login(client).headers["set-cookie"]
    monkeypatch.setenv("ENV", "production")
    assert "Secure" in login(client).headers["set-cookie"]
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert settings.cookie_secure() is True  # в production выключить нельзя


def test_rate_limit_is_per_ip_and_login_and_survives_in_db(client):
    make_admin()
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    blocked = login(client, password="wrong-password")
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    # верный пароль тоже блокируется, пока окно не истекло
    assert login(client).status_code == 429
    # другой логин с того же IP не заблокирован
    assert login(client, "other", "wrong-password").status_code == 401
    with SessionLocal() as db:
        assert db.query(LoginAttempt).count() >= 6


def test_rate_limit_window_expires_and_success_resets(client):
    make_admin()
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200  # успех сбрасывает счётчик
    with SessionLocal() as db:
        assert login_limiter.count_recent(db, "testclient", "admin") == 0
    for _ in range(5):
        login(client, password="wrong-password")
    assert login(client).status_code == 429
    with SessionLocal() as db:  # «состарим» попытки
        for a in db.scalars(select(LoginAttempt)):
            a.attempted_at -= timedelta(minutes=16)
        db.commit()
    assert login(client).status_code == 200


def test_unknown_login_does_not_leak_and_costs_a_hash(client, monkeypatch):
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda *a, **k: calls.append(1) or real(*a, **k))
    r = login(client, "nobody", "whatever-123")
    assert r.status_code == 401 and r.json()["detail"] == "Неверный логин или пароль"
    assert calls  # dummy-verify выполнен


def test_rehash_on_login_upgrades_old_parameters(client):
    from backend.app.database import SessionLocal
    from backend.app.models import Admin

    old = {**auth.PASSWORD_KDF}
    try:
        auth.PASSWORD_KDF["n"] = 2**10
        make_admin()
    finally:
        auth.PASSWORD_KDF.update(old)
    with SessionLocal() as db:
        before = db.scalar(select(Admin)).password_hash
    assert auth.needs_rehash(before)
    assert login(client).status_code == 200
    with SessionLocal() as db:
        after = db.scalar(select(Admin)).password_hash
    assert after != before and not auth.needs_rehash(after) and auth.verify_password(PASSWORD, after)


def test_production_kdf_parameters():
    # SEC-11: прод-параметры проверяются, даже если тесты используют облегчённые
    import importlib
    import os

    os.environ["SCRYPT_LOG_N"] = "16"
    try:
        fresh = importlib.reload(auth)
        assert fresh.PASSWORD_KDF["n"] == 2**16
        h = fresh.hash_password("SomeLongPassw0rd")
        assert fresh.verify_password("SomeLongPassw0rd", h) and not fresh.needs_rehash(h)
    finally:
        os.environ["SCRYPT_LOG_N"] = "12"
        importlib.reload(auth)


@pytest.mark.parametrize("pwd", ["short", "aaaaaaaaaaaa", "password12", "admin"])
def test_password_policy_rejects_weak(pwd):
    with pytest.raises(ValueError):
        auth.validate_password(pwd, "admin")


def test_password_cannot_equal_login():
    with pytest.raises(ValueError):
        auth.validate_password("administrator1", "Administrator1")


def test_change_password_revokes_other_sessions(client):
    make_admin()
    t1 = login(client).json()["access_token"]
    t2 = login(client).json()["access_token"]
    h1, h2 = {"Authorization": f"Bearer {t1}"}, {"Authorization": f"Bearer {t2}"}
    bad = client.post("/api/admin/password", headers=h1, json={"current_password": "nope-nope-1", "new_password": "NewPassw0rd!x"})
    assert bad.status_code == 403
    weak = client.post("/api/admin/password", headers=h1, json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    ok = client.post("/api/admin/password", headers=h1, json={"current_password": PASSWORD, "new_password": "NewPassw0rd!x"})
    assert ok.status_code == 204
    assert client.get("/api/admin/status", headers=h1).status_code == 200
    assert client.get("/api/admin/status", headers=h2).status_code == 401
    client.cookies.clear()
    assert login(client).status_code == 401
    assert login(client, password="NewPassw0rd!x").status_code == 200


def test_validate_for_startup_production(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET_FILE", str(tmp_path / "none.key"))
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ENABLE_DOCS", "true")
    problems = "\n".join(settings.validate_for_startup(settings.ROOT / "development.sqlite3"))
    for fragment in ("COOKIE_SECURE", "JWT_SECRET", "ALLOWED_HOSTS", "БД лежит внутри", "ENABLE_DOCS"):
        assert fragment in problems
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    monkeypatch.setenv("ALLOWED_HOSTS", "clubs.college.ru")
    monkeypatch.setenv("ENABLE_DOCS", "false")
    assert settings.validate_for_startup(tmp_path / "data" / "clubs.sqlite3") == []
