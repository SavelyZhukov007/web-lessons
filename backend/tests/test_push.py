"""Web Push: API подписок, хук уведомлений (с подменённым отправщиком) и реальный send_one против локального «push-сервера»."""
import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import PushSubscription
from backend.app.services import push as push_service

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401

MONDAY = "2026-11-02"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_keys():
    """Пара ключей «браузера»: p256dh (65 байт) + auth (16 байт), как у PushManager.subscribe()."""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, {"p256dh": b64(pub), "auth": b64(os.urandom(16))}


def sub_body(endpoint=ENDPOINT, club_id=None, keys=None):
    body = {"endpoint": endpoint, "keys": keys or make_keys()[1]}
    if club_id is not None:
        body["club_id"] = club_id
    return body


# ---------- публичный API ----------

def test_vapid_public_key_is_stable_and_valid(client):
    r1 = client.get("/api/push/vapid-public-key")
    assert r1.status_code == 200
    raw = base64.urlsafe_b64decode(r1.json()["publicKey"] + "==")
    assert len(raw) == 65 and raw[0] == 4
    assert client.get("/api/push/vapid-public-key").json() == r1.json()  # генерируется один раз


def test_vapid_private_key_not_exposed(client):
    keys = push_service.get_vapid_keys()
    assert keys.private_key not in client.get("/api/push/vapid-public-key").text


def test_subscribe_all_and_club_is_idempotent(admin_client):
    w = make_world(admin_client)
    admin_client.cookies.clear()  # подписка — публичная, без авторизации
    r = admin_client.post("/api/push/subscribe", json=sub_body())
    assert r.status_code == 201
    again = admin_client.post("/api/push/subscribe", json=sub_body())
    assert again.status_code == 200 and again.json()["status"] == "already-subscribed"
    c = admin_client.post("/api/push/subscribe", json=sub_body(club_id=w["club"]["id"]))
    assert c.status_code == 201
    with SessionLocal() as db:
        rows = list(db.scalars(select(PushSubscription)))
    assert len(rows) == 2 and sorted([r.club_id is None for r in rows]) == [False, True]


def test_subscribe_refreshes_keys_for_same_endpoint(client):
    client.post("/api/push/subscribe", json=sub_body())
    new = make_keys()[1]
    client.post("/api/push/subscribe", json={"endpoint": ENDPOINT, "keys": new})
    with SessionLocal() as db:
        row = db.scalar(select(PushSubscription))
        assert (row.p256dh, row.auth) == (new["p256dh"], new["auth"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.pop("endpoint"),
        lambda b: b.pop("keys"),
        lambda b: b.update(endpoint="not a url"),
        lambda b: b.update(endpoint="ftp://fcm.googleapis.com/x"),
        lambda b: b.update(endpoint="https://" + "a" * 2100 + ".com/x"),
        lambda b: b["keys"].update(p256dh="AAAA"),
        lambda b: b["keys"].update(auth="AAAA"),
        lambda b: b.update(club_id=0),
        lambda b: b.update(club_id="1"),
        lambda b: b.update(extra="x"),
    ],
)
def test_subscribe_validation_errors(client, mutate):
    body = sub_body()
    mutate(body)
    assert client.post("/api/push/subscribe", json=body).status_code == 422


def test_subscribe_rejects_ssrf_endpoints(client):
    for endpoint in (
        "https://evil.example/push",
        "http://fcm.googleapis.com/x",  # не https
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.evil.example/x",
        "https://localhost:8000/api/admin/logout",
    ):
        r = client.post("/api/push/subscribe", json=sub_body(endpoint=endpoint))
        assert r.status_code == 422, endpoint
    assert client.post("/api/push/subscribe", json=sub_body(endpoint="https://web.push.apple.com/Qabc")).status_code == 201
    assert client.post("/api/push/subscribe", json=sub_body(endpoint="https://updates.push.services.mozilla.com/wpush/v2/x")).status_code == 201


def test_subscribe_unknown_or_inactive_club_404(admin_client):
    w = make_world(admin_client)
    assert admin_client.post("/api/push/subscribe", json=sub_body(club_id=9999)).status_code == 404
    admin_client.patch(f"/api/admin/clubs/{w['club']['id']}", json={"is_active": False})
    assert admin_client.post("/api/push/subscribe", json=sub_body(club_id=w["club"]["id"])).status_code == 404


def test_unsubscribe_one_and_all(admin_client):
    w = make_world(admin_client)
    admin_client.post("/api/push/subscribe", json=sub_body())
    admin_client.post("/api/push/subscribe", json=sub_body(club_id=w["club"]["id"]))
    st = admin_client.post("/api/push/status", json={"endpoint": ENDPOINT}).json()
    assert st == {"all": True, "club_ids": [w["club"]["id"]], "announcements": True}
    r = admin_client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT, "club_id": w["club"]["id"]})
    assert r.status_code == 200 and r.json() == {"removed": 1, "remaining": 1}
    assert admin_client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}).json() == {"removed": 1, "remaining": 0}
    # повторно — не ошибка
    assert admin_client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}).json()["removed"] == 0


def test_subscribe_per_endpoint_limit(admin_client, monkeypatch):
    from backend.app.routers import push as push_router

    monkeypatch.setattr(push_router, "MAX_SUBSCRIPTIONS_PER_ENDPOINT", 2)
    w = make_world(admin_client)
    assert admin_client.post("/api/push/subscribe", json=sub_body()).status_code == 201
    assert admin_client.post("/api/push/subscribe", json=sub_body(club_id=w["club"]["id"])).status_code == 201
    other = _post(admin_client, "/api/admin/clubs", {"name": "Другой", "description": "", "category_id": w["category"]["id"], "leader_id": w["leader"]["id"], "is_active": True})
    assert admin_client.post("/api/push/subscribe", json=sub_body(club_id=other["id"])).status_code == 429


def test_deleting_club_cascades_subscriptions(admin_client):
    w = make_world(admin_client)
    admin_client.post("/api/push/subscribe", json=sub_body(club_id=w["club"]["id"]))
    admin_client.delete(f"/api/admin/clubs/{w['club']['id']}")
    with SessionLocal() as db:
        assert db.scalar(select(PushSubscription)) is None


# ---------- хук уведомлений (отправщик подменён) ----------

@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push_service, "send_one", lambda info, payload: calls.append((info["endpoint"], payload)))
    return calls


def _subscribe(client, endpoint, club_id=None):
    assert client.post("/api/push/subscribe", json=sub_body(endpoint=endpoint, club_id=club_id)).status_code in (200, 201)


def test_cancel_notifies_club_and_all_subscribers_only(admin_client, sent):
    w = make_world(admin_client)
    other = _post(admin_client, "/api/admin/clubs", {"name": "Другой", "description": "", "category_id": w["category"]["id"], "leader_id": w["leader"]["id"], "is_active": True})
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/club", w["club"]["id"])
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/all")
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/other", other["id"])
    r = admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": "Праздник"})
    assert r.status_code == 201  # BackgroundTasks в TestClient выполнены к моменту ответа
    assert sorted(e for e, _ in sent) == ["https://fcm.googleapis.com/fcm/send/all", "https://fcm.googleapis.com/fcm/send/club"]
    payload = sent[0][1]
    assert payload["kind"] == "cancelled" and "Python" in payload["title"] and "02.11" in payload["body"] and "Праздник" in payload["body"]
    assert payload["url"] == f"/club.html?id={w['club']['id']}"


def test_same_endpoint_subscribed_twice_gets_one_notification(admin_client, sent):
    w = make_world(admin_client)
    _subscribe(admin_client, ENDPOINT, w["club"]["id"])
    _subscribe(admin_client, ENDPOINT)
    admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": ""})
    assert len(sent) == 1


def test_move_and_patch_notify_but_comment_only_patch_does_not(admin_client, sent):
    w = make_world(admin_client)
    _subscribe(admin_client, ENDPOINT, w["club"]["id"])
    mv = _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": w["session"]["id"], "original_date": MONDAY, "type": "moved", "new_date": "2026-11-03",
        "new_start_time": "12:00", "new_end_time": "13:00", "new_room_id": w["room"]["id"], "comment": ""})
    assert len(sent) == 1 and sent[0][1]["kind"] == "moved" and "03.11" in sent[0][1]["body"] and "12:00–13:00" in sent[0][1]["body"]
    admin_client.patch(f"/api/admin/exceptions/{mv['id']}", json={"comment": "только комментарий"})
    assert len(sent) == 1
    admin_client.patch(f"/api/admin/exceptions/{mv['id']}", json={"new_date": "2026-11-04"})
    assert len(sent) == 2


def test_failing_sender_never_breaks_admin_request_and_others_still_get_it(admin_client, monkeypatch):
    w = make_world(admin_client)
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/bad", w["club"]["id"])
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/good", w["club"]["id"])
    delivered = []

    def flaky(info, payload):
        if info["endpoint"].endswith("bad"):
            raise RuntimeError("network down")
        delivered.append(info["endpoint"])

    monkeypatch.setattr(push_service, "send_one", flaky)
    r = admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": ""})
    assert r.status_code == 201
    assert delivered == ["https://fcm.googleapis.com/fcm/send/good"]
    with SessionLocal() as db:  # временная ошибка подписку НЕ удаляет
        assert len(list(db.scalars(select(PushSubscription)))) == 2


def test_gone_subscription_is_deleted(admin_client, monkeypatch):
    w = make_world(admin_client)
    _subscribe(admin_client, "https://fcm.googleapis.com/fcm/send/dead", w["club"]["id"])

    def gone(info, payload):
        raise push_service.PushGone("410")

    monkeypatch.setattr(push_service, "send_one", gone)
    admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": ""})
    with SessionLocal() as db:
        assert db.scalar(select(PushSubscription)) is None


def test_notify_unknown_exception_returns_zero(client):
    assert push_service.notify_exception(424242) == 0


# ---------- настоящий send_one → локальный push-сервис, расшифровка aes128gcm ----------

class _FakePushService:
    def __init__(self, status=201):
        self.requests = []
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": self.rfile.read(length)})
                self.send_response(outer.status)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server.server_port}/push/xyz"


def test_real_send_one_encrypts_signs_and_posts(monkeypatch):
    import http_ece
    import jwt as pyjwt

    monkeypatch.setenv("PUSH_ALLOWED_HOSTS", "127.0.0.1")
    client_key, keys = make_keys()
    with _FakePushService() as svc:
        assert push_service.endpoint_allowed(svc.endpoint)
        push_service.send_one({"endpoint": svc.endpoint, "keys": keys}, {"title": "Привет", "body": "Занятие отменено"})
        req = svc.requests[0]
    assert req["headers"]["content-encoding"] == "aes128gcm" and "ttl" in req["headers"]
    plaintext = http_ece.decrypt(req["body"], private_key=client_key, auth_secret=base64.urlsafe_b64decode(keys["auth"] + "=="), version="aes128gcm")
    assert json.loads(plaintext.decode()) == {"title": "Привет", "body": "Занятие отменено"}
    # VAPID: подпись проверяется публичным ключом сервера
    auth = req["headers"]["authorization"]
    assert auth.startswith("vapid t=")
    token = auth.split("t=")[1].split(",")[0]
    pub = push_service.get_vapid_keys().public_key
    assert f"k={pub}" in auth
    point = base64.urlsafe_b64decode(pub + "==")
    pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    claims = pyjwt.decode(token, pub_key, algorithms=["ES256"], audience=f"http://127.0.0.1:{svc.server.server_port}")
    assert claims["sub"].startswith("mailto:")


@pytest.mark.parametrize("status,gone", [(410, True), (404, True), (500, False)])
def test_real_send_one_maps_http_errors(monkeypatch, status, gone):
    monkeypatch.setenv("PUSH_ALLOWED_HOSTS", "127.0.0.1")
    _, keys = make_keys()
    with _FakePushService(status=status) as svc:
        with pytest.raises(push_service.PushGone if gone else Exception) as exc:
            push_service.send_one({"endpoint": svc.endpoint, "keys": keys}, {"x": 1})
    assert isinstance(exc.value, push_service.PushGone) == gone


def test_vapid_keys_from_env_and_file_permissions(monkeypatch, tmp_path):
    keyfile = tmp_path / "keys.json"
    monkeypatch.setenv("VAPID_KEYS_FILE", str(keyfile))
    k1 = push_service.get_vapid_keys()
    assert keyfile.exists() and (keyfile.stat().st_mode & 0o077 == 0 or os.name == "nt")
    assert push_service.get_vapid_keys() == k1
    monkeypatch.setenv("VAPID_PRIVATE_KEY", k1.private_key)
    assert push_service.get_vapid_keys().public_key == k1.public_key


def test_vapid_files_are_gitignored():
    from backend.app.settings import ROOT

    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for name in ("vapid_keys.json", "jwt_secret.key", ".env"):
        assert name in ignore
