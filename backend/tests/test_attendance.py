"""Анонимная посещаемость (phase 2 F): QR преподавателя, отметка по ID студента, срок, повтор, чужое занятие, 21 день, доступ."""
from __future__ import annotations

import base64
import hashlib

import pytest
import hmac
import secrets
from datetime import date, datetime, timedelta

from backend.app.routers import attendance as att
from backend.app.services.clock import MSK

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401
from .test_session_club_conflicts_api import _second_club, _session

MONDAY = "2027-11-01"


def student_id(secret: bytes, fio: str, group: str) -> str:
    """Эталон алгоритма приложения (app-student.js): S- + base32(HMAC-SHA256(secret, норм. ФИО|группа))[:128 бит]."""
    msg = (" ".join(fio.lower().replace("ё", "е").split()) + "|" + group.upper().replace(" ", "")).encode()
    raw = base64.b32encode(hmac.new(secret, msg, hashlib.sha256).digest()[:16]).decode().rstrip("=")
    return "S-" + "-".join(raw[i:i + 4] for i in range(0, 26, 4))


DEV1 = "d" * 43
DEV2 = "e" * 43
_CLOCK = {}


def set_clock(day=MONDAY, hm="10:02", sec=0):
    """Подменить «сейчас» в роутере посещаемости (занятие make_world — 10:00–11:30 по понедельникам)."""
    _CLOCK["now"] = datetime.combine(date.fromisoformat(day), datetime.strptime(hm, "%H:%M").time(), MSK) + timedelta(seconds=sec)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    set_clock()
    monkeypatch.setattr(att, "now_msk", lambda: _CLOCK["now"])


SID = student_id(b"\x01" * 32, "Петрова Анна", "1ИСИП-126")
SID2 = student_id(b"\x02" * 32, "Петрова Анна", "1ИСИП-126")


def _qr(client, session_id, day=MONDAY):
    r = client.post("/api/admin/attendance/qr", json={"session_id": session_id, "date": day})
    assert r.status_code == 200, r.text
    return r.json()


def _checkin(client, sid, session_id, token, nonce=None, dev=None):
    return client.post("/api/attendance/checkin", json={"student_id": sid, "session_id": session_id, "qr_token": token,
                                                         "nonce": nonce or secrets.token_urlsafe(16),
                                                         "device_token": dev or ("d" if sid == SID else "e") * 43})


def test_student_id_determinism_and_uniqueness():
    assert SID == student_id(b"\x01" * 32, "  петрова   анна ", "1исип-126")  # тот же секрет + то же ФИО → тот же ID
    assert SID != SID2  # другой секрет устройства → другой ID (по имени не вычислить)
    assert SID != student_id(b"\x01" * 32, "Петрова Анна", "2ИСИП-126")
    assert att.normalize_student_id(SID.lower().replace("-", " ")) == SID
    assert len({student_id(secrets.token_bytes(32), "Иванов Иван", "1ИСИП-126") for _ in range(200)}) == 200


def test_qr_and_checkin_flow(admin_client):
    w = make_world(admin_client)
    qr = _qr(admin_client, w["session"]["id"])
    assert qr["state"] == "open" and qr["token"].startswith("itc-att2.") and qr["ttl"] == 60 and qr["rotate"] <= 30 and qr["club_name"] == "Python"
    r = _checkin(admin_client, SID, w["session"]["id"], qr["token"])
    assert r.status_code == 201, r.text
    assert r.json()["student_id"] == SID and "name" not in r.json()
    dup = _checkin(admin_client, SID, w["session"]["id"], qr["token"])
    assert dup.status_code == 409 and "Уже отмечен" in dup.json()["detail"]
    assert _checkin(admin_client, SID2, w["session"]["id"], qr["token"]).status_code == 201
    lst = admin_client.get(f"/api/admin/attendance?session_id={w['session']['id']}&date={MONDAY}").json()
    assert [x["student_id"] for x in lst] == [SID, SID2] and lst[0]["short"].startswith("S-")


def test_replay_nonce_rejected(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    assert _checkin(admin_client, SID, w["session"]["id"], tok, nonce="n" * 20).status_code == 201
    r = _checkin(admin_client, SID2, w["session"]["id"], tok, nonce="n" * 20)
    assert r.status_code == 409 and "Повторная" in r.json()["detail"]


def test_forged_and_garbage_tokens_rejected(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    body, sig = tok[len(att.PREFIX):].split(".")
    forged = att.PREFIX + att._b64(att._unb64(body).replace(b'"2027-11-01"', b'"2027-11-08"')) + "." + sig
    for t in [forged, "hello-world-123", tok[:-2] + "AA", "itc-att1.abc.def"]:
        assert _checkin(admin_client, SID, w["session"]["id"], t).status_code == 400, t


def test_qr_expires_in_60s(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    set_clock(sec=61)
    r = _checkin(admin_client, SID, w["session"]["id"], tok)
    assert r.status_code == 410 and "устарел" in r.json()["detail"]


def test_cross_session_misuse(admin_client):
    w = make_world(admin_client)
    room2 = _post(admin_client, "/api/admin/rooms", {"name": "202", "building": "Главный", "capacity": 10})
    c2 = _second_club(admin_client, w, name="Шахматы")
    s2 = _session(admin_client, c2, room2, 1, "12:00", "13:00").json()
    tok = _qr(admin_client, w["session"]["id"])["token"]
    r = _checkin(admin_client, SID, s2["id"], tok)
    assert r.status_code == 409 and "другому занятию" in r.json()["detail"]


def test_bad_student_id(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    for bad in ["Анна Петрова", "S-1234", "T-" + SID[2:]]:
        assert _checkin(admin_client, bad, w["session"]["id"], tok).status_code == 422


def test_cancelled_occurrence(admin_client):
    w = make_world(admin_client)
    _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": w["session"]["id"], "original_date": MONDAY, "comment": ""})
    r = admin_client.post("/api/admin/attendance/qr", json={"session_id": w["session"]["id"], "date": MONDAY})
    assert r.status_code == 409


def _mine(client, sid=SID, dev=DEV1):
    return client.get("/api/attendance/mine", headers={"X-Student-Id": sid, "X-Device-Token": dev})


def test_window_early_and_closed(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    set_clock(hm="09:59", sec=40)  # за 20 с до начала — ещё рано
    q = _qr(admin_client, sid)
    assert q["state"] == "early" and "token" not in q and 9 <= q["opens_in"] <= 11
    set_clock(hm="09:59", sec=51)  # за 9 с — открыт
    assert _qr(admin_client, sid)["state"] == "open"
    set_clock(hm="10:14", sec=30)
    tok = _qr(admin_client, sid)["token"]
    set_clock(hm="10:15", sec=0)
    assert _checkin(admin_client, SID, sid, tok).status_code == 201  # ровно 15-я минута — ещё можно
    set_clock(hm="10:15", sec=5)
    assert _qr(admin_client, sid)["state"] == "closed"
    r = _checkin(admin_client, SID2, sid, tok)
    assert r.status_code in (403, 410)
    tok2 = att.make_token(sid, MONDAY, now=_CLOCK["now"].timestamp())[0]  # даже свежий подписанный токен вне окна
    r = _checkin(admin_client, SID2, sid, tok2)
    assert r.status_code == 403 and r.json()["detail"] == "Отметка закрыта"


def test_device_proof_for_mine(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    assert _mine(admin_client).status_code == 403  # ещё не отмечался — устройство не зарегистрировано
    assert _checkin(admin_client, SID, w["session"]["id"], tok).status_code == 201
    h = _mine(admin_client)
    assert h.status_code == 200 and h.json()["retention_days"] == 21 and h.json()["items"][0]["club_name"] == "Python"
    assert _mine(admin_client, dev=DEV2).status_code == 403  # чужое устройство
    assert _mine(admin_client, dev="short").status_code == 403
    # чужой ID с другого устройства не отметить (ID привязан к первому устройству)
    r = _checkin(admin_client, SID, w["session"]["id"], tok, dev=DEV2)
    assert r.status_code == 403
    assert admin_client.get("/api/attendance/history?student_id=" + SID).status_code in (404, 405)  # публичной проверки нет


def test_manual_admin_lookup_delete_and_purge(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    r = admin_client.post("/api/admin/attendance/manual", json={"session_id": sid, "date": MONDAY, "student_id": SID.lower()})
    assert r.status_code == 201
    h = admin_client.get(f"/api/admin/attendance/student?student_id={SID}").json()
    assert h["items"][0]["method"] == "manual"
    live = admin_client.get(f"/api/admin/attendance/live?session_id={sid}&date={MONDAY}").json()
    assert live["count"] == 1
    assert admin_client.get(f"/api/admin/attendance/live?session_id={sid}&date={MONDAY}&since_id={live['items'][0]['id']}").json()["items"] == []
    assert admin_client.delete(f"/api/admin/attendance/{live['items'][0]['id']}").status_code == 204
    assert admin_client.get(f"/api/admin/attendance/student?student_id={SID}").json()["items"] == []
    admin_client.post("/api/admin/attendance/manual", json={"session_id": sid, "date": MONDAY, "student_id": SID})
    # 21 день: через 21 день ещё хранится, через 22 — удаляется при обращении
    set_clock(day=(date.fromisoformat(MONDAY) + timedelta(days=21)).isoformat(), hm="00:00")
    assert len(admin_client.get(f"/api/admin/attendance/student?student_id={SID}").json()["items"]) == 1
    set_clock(day=(date.fromisoformat(MONDAY) + timedelta(days=22)).isoformat(), hm="00:00")
    assert admin_client.get(f"/api/admin/attendance/student?student_id={SID}").json()["items"] == []


def test_stats_and_access(admin_client):
    w = make_world(admin_client)
    tok = _qr(admin_client, w["session"]["id"])["token"]
    _checkin(admin_client, SID, w["session"]["id"], tok)
    _checkin(admin_client, SID2, w["session"]["id"], tok)
    s = admin_client.get("/api/admin/attendance/stats?date_from=2027-10-01&date_to=2027-11-30").json()
    assert s["total"] == 2 and s["clubs"][0]["average"] == 2.0
    client = admin_client
    client.cookies.clear()
    for path in ["/api/admin/attendance/stats", f"/api/admin/attendance?session_id=1&date={MONDAY}", f"/api/admin/attendance/student?student_id={SID}", f"/api/admin/attendance/live?session_id=1&date={MONDAY}"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/admin/attendance/qr", json={"session_id": 1, "date": MONDAY}).status_code == 401
