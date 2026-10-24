"""Доступ преподавателей: T-токен (случайный, в БД только SHA-256), перевыпуск/отзыв, сессия scope=teacher, только свои кружки."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.models import Leader
from backend.app.routers import teacher as tch

from .test_attendance import MONDAY, SID, _checkin, _fixed_clock, set_clock  # noqa: F401
from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401
from .test_session_club_conflicts_api import _second_club, _session


def _login(client, token):
    return client.post("/api/teacher/login", json={"token": token})


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_token_random_hash_only_and_login(admin_client):
    w = make_world(admin_client)
    r = admin_client.post(f"/api/admin/leaders/{w['leader']['id']}/access")
    assert r.status_code == 200
    tok = r.json()["token"]
    assert tok.startswith("T-") and len(tok.replace("-", "")) == 27
    assert tch.new_access_token() != tch.new_access_token()
    with SessionLocal() as db:
        l = db.get(Leader, w["leader"]["id"])
        assert l.access_hash == tch.hash_access(tok) and tok not in str(l.__dict__)
    assert "token" not in str(admin_client.get("/api/admin/teachers").json())
    lg = _login(admin_client, tok.lower().replace("-", " "))
    assert lg.status_code == 200 and lg.json()["teacher"]["name"] == w["leader"]["name"]
    assert _login(admin_client, tch.new_access_token()).status_code == 401
    assert _login(admin_client, "T-NOPE").status_code in (401, 422)


def test_create_teacher_endpoint(admin_client, client):
    r = admin_client.post("/api/admin/teachers", json={"name": "  Иванов   Пётр Сергеевич "})
    assert r.status_code == 201 and r.json()["name"] == "Иванов Пётр Сергеевич" and r.json()["token"].startswith("T-")
    admin_client.cookies.clear()
    assert admin_client.post("/api/admin/teachers", json={"name": "Хакер"}).status_code == 401


def test_reissue_and_revoke(admin_client):
    w = make_world(admin_client)
    lid = w["leader"]["id"]
    t1 = admin_client.post(f"/api/admin/leaders/{lid}/access").json()["token"]
    sess = _login(admin_client, t1).json()["access_token"]
    assert admin_client.get("/api/teacher/me", headers=_auth(sess)).status_code == 200
    t2 = admin_client.post(f"/api/admin/leaders/{lid}/access").json()["token"]
    assert _login(admin_client, t1).status_code == 401  # старый идентификатор недействителен
    assert admin_client.get("/api/teacher/me", headers=_auth(sess)).status_code == 401  # и старая сессия тоже
    sess2 = _login(admin_client, t2).json()["access_token"]
    assert admin_client.delete(f"/api/admin/leaders/{lid}/access").status_code == 204
    assert admin_client.get("/api/teacher/me", headers=_auth(sess2)).status_code == 401
    assert _login(admin_client, t2).status_code == 401


def test_role_scoping(admin_client):
    w = make_world(admin_client)
    other = _post(admin_client, "/api/admin/leaders", {"name": "Чужой", "position": "", "contact": ""})
    room2 = _post(admin_client, "/api/admin/rooms", {"name": "202", "building": "Главный", "capacity": 10})
    c2 = _second_club(admin_client, w, name="Шахматы", leader_id=other["id"])
    s2 = _session(admin_client, c2, room2, 1, "12:00", "13:00").json()
    tok = admin_client.post(f"/api/admin/leaders/{w['leader']['id']}/access").json()["token"]
    h = _auth(_login(admin_client, tok).json()["access_token"])
    me = admin_client.get("/api/teacher/me", headers=h).json()
    assert [c["name"] for c in me["clubs"]] == ["Python"] and all(s["club_id"] != c2["id"] for s in me["sessions"])
    own = w["session"]["id"]
    qr = admin_client.post("/api/teacher/attendance/qr", json={"session_id": own, "date": MONDAY}, headers=h)
    assert qr.status_code == 200
    assert _checkin(admin_client, SID, own, qr.json()["token"]).status_code == 201
    lst = admin_client.get(f"/api/teacher/attendance?session_id={own}&date={MONDAY}", headers=h).json()
    assert lst["count"] == 1 and lst["items"][0]["short"].startswith("S-")
    # живой список: удалить отметку (своё занятие)
    item = lst["items"][0]["id"]
    # чужое занятие: QR, список, ручная отметка, удаление — 403/404
    assert admin_client.post("/api/teacher/attendance/qr", json={"session_id": s2["id"], "date": MONDAY}, headers=h).status_code == 403
    assert admin_client.get(f"/api/teacher/attendance?session_id={s2['id']}&date={MONDAY}", headers=h).status_code == 403
    assert admin_client.post("/api/teacher/attendance/manual", json={"session_id": s2["id"], "date": MONDAY, "student_id": SID}, headers=h).status_code == 403
    other_qr = admin_client.post("/api/admin/attendance/qr", json={"session_id": s2["id"], "date": MONDAY}).json()
    assert other_qr["state"] == "early"
    set_clock(hm="12:02")
    other_tok = admin_client.post("/api/admin/attendance/qr", json={"session_id": s2["id"], "date": MONDAY}).json()["token"]
    assert _checkin(admin_client, SID, s2["id"], other_tok).status_code == 201
    foreign = admin_client.get(f"/api/admin/attendance?session_id={s2['id']}&date={MONDAY}").json()[0]["id"]
    assert admin_client.delete(f"/api/teacher/attendance/{foreign}", headers=h).status_code == 404
    # расписание преподаватель не меняет (только администратор)
    for path in ("/api/teacher/exceptions/cancellations", "/api/teacher/exceptions/moves"):
        assert admin_client.post(path, json={"session_id": own, "original_date": MONDAY}, headers=h).status_code in (404, 405)
    assert admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": own, "original_date": MONDAY, "comment": ""},
                             headers=h, cookies={}).status_code in (201, 401)
    # ручная отметка — только во время занятия (10:00–11:30); в 12:02 уже нельзя
    r = admin_client.post("/api/teacher/attendance/manual", json={"session_id": own, "date": MONDAY, "student_id": SID}, headers=h)
    assert r.status_code == 403
    set_clock(hm="11:00")
    assert admin_client.post("/api/teacher/attendance/manual", json={"session_id": own, "date": MONDAY, "student_id": SID}, headers=h).status_code == 409
    # удалить свою отметку
    assert admin_client.delete(f"/api/teacher/attendance/{item}", headers=h).status_code == 204
    assert admin_client.get(f"/api/teacher/attendance?session_id={own}&date={MONDAY}", headers=h).json()["count"] == 0


def test_teacher_cannot_use_admin_api(client):
    w_client = client
    assert w_client.get("/api/teacher/me").status_code == 401
    assert w_client.get("/api/teacher/me", headers=_auth("tch1.e30.xxx")).status_code == 401
