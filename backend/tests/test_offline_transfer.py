"""t100: офлайн-очередь отметок (scanned_at) и одноразовый QR переноса аккаунта преподавателя."""
from __future__ import annotations

import secrets

from backend.app.routers import attendance as att
from backend.app.routers import teacher as tch

from .test_attendance import _CLOCK, MONDAY, SID, SID2, _fixed_clock, _qr, set_clock  # noqa: F401
from .test_exception_conflicts_api import admin_client, make_world  # noqa: F401


def _ci(client, sid, session_id, token, scanned_at=None):
    body = {"student_id": sid, "session_id": session_id, "qr_token": token, "nonce": secrets.token_urlsafe(16),
            "device_token": ("d" if sid == SID else "e") * 43}
    if scanned_at is not None:
        body["scanned_at"] = scanned_at
    return client.post("/api/attendance/checkin", json=body)


def test_offline_checkin_validated_at_scan_time(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    set_clock(hm="10:05")
    tok = _qr(admin_client, sid)["token"]
    scanned = _CLOCK["now"].timestamp()
    set_clock(hm="12:30")  # связь появилась через 2,5 ч: токен давно истёк и окно закрыто, но на момент скана всё было валидно
    assert _ci(admin_client, SID, sid, tok).status_code in (403, 410)  # без scanned_at — как раньше, отказ
    r = _ci(admin_client, SID, sid, tok, scanned_at=scanned)
    assert r.status_code == 201, r.text
    # подделка времени: токен на момент «скана» ещё не существовал / уже истёк
    assert _ci(admin_client, SID2, sid, tok, scanned_at=scanned - 3600).status_code in (400, 410)
    assert _ci(admin_client, SID2, sid, tok, scanned_at=scanned + 3600).status_code == 410
    # будущее и слишком большая задержка
    assert _ci(admin_client, SID2, sid, tok, scanned_at=_CLOCK["now"].timestamp() + 3600).status_code == 400
    set_clock(hm="10:05")
    tok2 = _qr(admin_client, sid)["token"]
    s2 = _CLOCK["now"].timestamp()
    set_clock(hm="17:00")
    assert _ci(admin_client, SID2, sid, tok2, scanned_at=s2).status_code == 410


def test_offline_window_enforced_at_scan_time(admin_client):
    w = make_world(admin_client)
    sid = w["session"]["id"]
    set_clock(hm="10:20")  # окно (15 мин) уже закрыто в момент скана
    tok = att.make_token(sid, MONDAY, now=_CLOCK["now"].timestamp())[0]
    s = _CLOCK["now"].timestamp()
    set_clock(hm="10:21")
    r = _ci(admin_client, SID, sid, tok, scanned_at=s)
    assert r.status_code == 403 and r.json()["detail"] == "Отметка закрыта"


def test_transfer_qr_one_time(admin_client):
    w = make_world(admin_client)
    lid = w["leader"]["id"]
    t1 = admin_client.post(f"/api/admin/leaders/{lid}/access").json()["token"]
    old = admin_client.post("/api/teacher/login", json={"token": t1}).json()["access_token"]
    code = admin_client.post(f"/api/admin/leaders/{lid}/transfer").json()["code"]
    assert code.startswith("itc-tx1.")
    r = admin_client.post("/api/teacher/transfer", json={"code": code})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["token"].startswith("T-") and new["token"] != t1
    assert admin_client.get("/api/teacher/me", headers={"Authorization": "Bearer " + new["access_token"]}).status_code == 200
    assert admin_client.get("/api/teacher/me", headers={"Authorization": "Bearer " + old}).status_code == 401  # старый телефон отключён
    assert admin_client.post("/api/teacher/login", json={"token": t1}).status_code == 401
    assert admin_client.post("/api/teacher/transfer", json={"code": code}).status_code == 401  # повторно нельзя
    assert admin_client.post("/api/teacher/transfer", json={"code": code[:-2] + "AA"}).status_code == 401
    admin_client.cookies.clear()
    assert admin_client.post(f"/api/admin/leaders/{lid}/transfer").status_code == 401


def test_transfer_expires(admin_client, monkeypatch):
    w = make_world(admin_client)
    lid = w["leader"]["id"]
    admin_client.post(f"/api/admin/leaders/{lid}/access")
    code = admin_client.post(f"/api/admin/leaders/{lid}/transfer").json()["code"]
    real = tch.time.time
    monkeypatch.setattr(tch.time, "time", lambda: real() + tch.TRANSFER_TTL + 5)
    assert admin_client.post("/api/teacher/transfer", json={"code": code}).status_code == 401
