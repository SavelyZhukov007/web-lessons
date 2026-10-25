"""FCM (HTTP v1) для APK: регистрация установки, адресация, очистка мёртвых токенов, выключение без настройки.
Сеть не трогаем: подменяется fcm.send_one / fcm._post, ключ сервисного аккаунта — сгенерированный в тесте."""
from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import AppDevice
from backend.app.services import broadcast as service
from backend.app.services import client_logs, delivery, fcm
from backend.app.services import push as push_service

from .test_broadcasts import msg, second_club
from .test_exception_conflicts_api import admin_client, make_world  # noqa: F401
from .test_push import MONDAY

TOKEN = "tok_" + "A" * 40


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    client_logs.reset_limits()
    fcm.reset()
    monkeypatch.delenv("FCM_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr(push_service, "send_one", lambda info, data: None)
    yield
    fcm.reset()
    client_logs.reset_limits()


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    p = tmp_path / "fcm-key.json"
    p.write_text(json.dumps({"type": "service_account", "project_id": "kipclub-test", "private_key_id": "x", "private_key": pem,
                             "client_email": "bot@kipclub-test.iam.gserviceaccount.com", "client_id": "1",
                             "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setenv("FCM_CREDENTIALS_FILE", str(p))
    return p


@pytest.fixture
def fcm_sent(key_file, monkeypatch):
    calls = []
    monkeypatch.setattr(fcm, "send_one", lambda token, data, collapse=None: calls.append((token, data, collapse)))
    return calls


def reg(client, dev="d" * 20, token=TOKEN, **kw):
    body = {"device_id": dev, "token": token, "platform": "android", "app_version": "0.7.014", **kw}
    return client.post("/api/app/devices", json=body)


def device(dev="d" * 20) -> AppDevice:
    with SessionLocal() as db:
        return db.get(AppDevice, service.device_key(dev))


def test_register_validates_and_stores(client):
    assert reg(client, club_ids=[3, 1, 3], changes=False).status_code == 204
    d = device()
    assert d.fcm_token == TOKEN and json.loads(d.club_ids) == [1, 3] and d.notify_changes is False and d.app_version == "0.7.014"
    for bad in ({"dev": "short"}, {"token": "bad token!"}, {"platform": "ios"}, {"club_ids": list(range(101))}):
        kw = dict(bad)
        assert reg(client, kw.pop("dev", "d" * 20), **kw).status_code == 422


def test_token_moves_between_installs_and_can_be_cleared(client):
    reg(client, "a" * 20)
    reg(client, "b" * 20)  # тот же токен (переустановка) — у старой установки снимается
    assert device("a" * 20).fcm_token is None and device("b" * 20).fcm_token == TOKEN
    reg(client, "b" * 20, token=None)
    assert device("b" * 20).fcm_token is None


def test_register_rate_limited(client):
    codes = [reg(client, f"{i:020d}").status_code for i in range(client_logs.RATE + 1)]
    assert codes[-1] == 429 and codes[0] == 204


def test_disabled_when_unconfigured(admin_client, monkeypatch):
    monkeypatch.setattr(fcm, "send_one", lambda *a, **k: pytest.fail("FCM не должен вызываться"))
    reg(admin_client)
    assert not fcm.enabled()
    r = admin_client.post("/api/admin/broadcasts", json=msg()).json()
    assert r["fcm_sent"] == 0
    monkeypatch.setenv("FCM_CREDENTIALS_FILE", "/nonexistent/fcm.json")
    assert not fcm.enabled()


def test_broadcast_targets_by_clubs_and_prefs(admin_client, fcm_sent):
    w = make_world(admin_client)
    other = second_club(admin_client, w)
    reg(admin_client, "a" * 20, "tok_" + "a" * 30, club_ids=[w["club"]["id"]])
    reg(admin_client, "b" * 20, "tok_" + "b" * 30, club_ids=[other["id"]])
    reg(admin_client, "c" * 20, "tok_" + "c" * 30, club_ids=[w["club"]["id"]], announcements=False)
    est = admin_client.post("/api/admin/broadcasts/estimate", json={"audience": "clubs", "club_ids": [w["club"]["id"]]}).json()
    assert est["fcm"] == 1
    r = admin_client.post("/api/admin/broadcasts", json=msg(audience="clubs", club_ids=[w["club"]["id"]])).json()
    assert r["fcm_sent"] == 1 and [t for t, _, _ in fcm_sent] == ["tok_" + "a" * 30]
    _, data, collapse = fcm_sent[0]
    assert data["type"] == "announcement" and data["id"] == r["id"] and collapse == data["tag"]
    admin_client.post("/api/admin/broadcasts", json=msg("key-00000002"))
    assert len(fcm_sent) == 3  # «всем»: a и b, c отключил объявления


def test_exception_goes_to_followers_with_changes_on(admin_client, fcm_sent):
    w = make_world(admin_client)
    reg(admin_client, "a" * 20, "tok_" + "a" * 30, club_ids=[w["club"]["id"]])
    reg(admin_client, "b" * 20, "tok_" + "b" * 30, club_ids=[w["club"]["id"]], changes=False)
    reg(admin_client, "c" * 20, "tok_" + "c" * 30, club_ids=[])
    admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": MONDAY,
                                                                    "type": "cancelled", "comment": ""})
    assert [t for t, _, _ in fcm_sent] == ["tok_" + "a" * 30]
    data = fcm_sent[0][1]
    assert data["type"] == "cancel" and data["session_id"] == w["session"]["id"] and data["original_date"] == MONDAY


def test_gone_token_is_cleared_and_errors_dont_break(admin_client, key_file, monkeypatch):
    reg(admin_client, "a" * 20, "tok_" + "a" * 30)
    reg(admin_client, "b" * 20, "tok_" + "b" * 30)

    def boom(token, data, collapse=None):
        raise fcm.FcmGone("404") if token.startswith("tok_a") else RuntimeError("500")
    monkeypatch.setattr(fcm, "send_one", boom)
    r = admin_client.post("/api/admin/broadcasts", json=msg())
    assert r.status_code == 201 and r.json()["fcm_failed"] == 2
    assert device("a" * 20).fcm_token is None and device("b" * 20).fcm_token is not None


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


@pytest.mark.parametrize("status,body,exc", [
    (200, {}, None), (404, None, fcm.FcmGone),
    (400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"errorCode": "UNREGISTERED"}]}}, fcm.FcmGone),
    (404, {"error": {"status": "NOT_FOUND"}}, fcm.FcmGone), (500, None, RuntimeError),
])
def test_real_send_one_builds_v1_message(key_file, monkeypatch, status, body, exc):
    posted = {}
    monkeypatch.setattr(fcm, "_access_token", lambda: ("at", fcm._load()[1]))
    monkeypatch.setattr(fcm, "_post", lambda url, headers, b: posted.update(url=url, headers=headers, body=b) or Resp(status, body))
    if exc:
        with pytest.raises(exc):
            fcm.send_one(TOKEN, {"type": "cancel", "n": 5, "x": None}, "exception-1")
    else:
        fcm.send_one(TOKEN, {"type": "cancel", "n": 5, "x": None}, "exception-1")
    assert posted["url"] == "https://fcm.googleapis.com/v1/projects/kipclub-test/messages:send"
    assert posted["headers"]["Authorization"] == "Bearer at"
    m = posted["body"]["message"]
    assert m["token"] == TOKEN and m["data"] == {"type": "cancel", "n": "5", "x": ""}
    assert m["android"]["priority"] == "HIGH" and m["android"]["collapse_key"] == "exception-1"


def test_access_token_refreshes_once_and_load_requires_config(key_file, monkeypatch):
    from google.oauth2 import service_account
    calls = []

    def refresh(self, request):
        calls.append(1)
        self.token = "fresh"
        self.expiry = None
    monkeypatch.setattr(service_account.Credentials, "refresh", refresh)
    monkeypatch.setattr(service_account.Credentials, "valid", property(lambda self: self.token is not None))
    assert fcm._access_token() == ("fresh", "kipclub-test")
    assert fcm._access_token() == ("fresh", "kipclub-test") and len(calls) == 1
    monkeypatch.delenv("FCM_CREDENTIALS_FILE")
    with pytest.raises(RuntimeError):
        fcm._load()


def test_post_uses_requests(monkeypatch):
    import requests
    seen = {}
    monkeypatch.setattr(requests, "post", lambda url, headers, json, timeout: seen.update(url=url, t=timeout) or "ok")
    assert fcm._post("u", {}, {}) == "ok" and seen == {"url": "u", "t": 10}


def test_channel_crash_is_contained(admin_client, key_file, monkeypatch):
    monkeypatch.setattr(delivery, "fcm_targets", lambda db, ev: 1 / 0)
    assert admin_client.post("/api/admin/broadcasts", json=msg()).status_code == 201


def test_stale_devices_ignored(admin_client, fcm_sent):
    from datetime import timedelta
    reg(admin_client)
    with SessionLocal() as db:
        d = db.scalars(select(AppDevice)).one()
        d.last_seen = d.last_seen - timedelta(days=delivery.DEVICE_ACTIVE_DAYS + 1)
        db.commit()
    admin_client.post("/api/admin/broadcasts", json=msg())
    assert fcm_sent == []
