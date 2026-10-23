from __future__ import annotations
import pytest
from sqlalchemy import select
from backend.app.auth import hash_password
from backend.app.database import SessionLocal
from backend.app.models.admin import Admin
from backend.app.models.session_exception import SessionException
from backend.app.routers import admin as admin_router

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "Password123"


@pytest.fixture(autouse=True)
def isolated_login_attempts(monkeypatch):
    # Не наследуем блокировку IP из тестов ограничения попыток входа.
    monkeypatch.setattr(admin_router, "login_attempts_by_ip", {})


@pytest.fixture
def admin_client(client):
    with SessionLocal() as db:
        db.add(Admin(login = ADMIN_LOGIN, password_hash = hash_password(ADMIN_PASSWORD)))
        db.commit()
    resp = client.post(
        "/api/admin/login",
        json = {"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return client


def _post(client, url, payload):
    resp = client.post(url, json = payload)
    assert resp.status_code == 201, f"{url}: {resp.status_code} {resp.text}"
    return resp.json()

def make_world(client, *, weekday = 1, start = "10:00", end = "11:00"):
    cat = _post(client, "/api/admin/categories", 
                {"name": "Программирование", "color": "#2563eb"})
    leader = _post(client, "/api/admin/leaders", 
                {"name": "Иван Иванов", "position": "Преподаватель", "contact": "ivan@test.local"})
    room = _post(client, "/api/admin/rooms", 
                {"name": "101", "building": "Главный", "capacity": 20})
    club = _post(client, "/api/admin/clubs", 
                {"name": "Python", "description": "Базовый",
                 "category_id": cat["id"], "leader_id": leader["id"], "is_active": True})
    session = _post(client, "/api/admin/sessions",
                {"club_id": club["id"], "room_id": room["id"], "weekday": weekday, 
                 "start_time": start, "end_time": end})
    return {"category": cat, "leader": leader, "room": room, "club": club, "session": session}

def add_extra_world(client, *, weekday, start, end, room_id=None, leader_id=None, name="Конкурент"):
    cat = _post(client, "/api/admin/categories", 
                {"name": f"Кат-{name}", "color": "#dc2626"})
    leader = _post(client, "/api/admin/leaders", 
                {"name": f"Рук-{name}", "position": "", "contact": ""})
    if room_id is None:
        room = _post(client, "/api/admin/rooms", 
                    {"name": f"Комн-{name}", "building": "B", "capacity": 10})
    else:
        room = {"id": room_id}
    club = _post(client, "/api/admin/clubs", 
                {"name": name, "description": "",
                 "category_id": cat["id"], "leader_id": leader_id or leader["id"], "is_active": True})
    session = _post(client, "/api/admin/sessions",
            {"club_id": club["id"], "room_id": room["id"],
             "weekday": weekday, "start_time": start, "end_time": end})
    return {"category": cat, "leader": leader, "room": room, "club": club, "session": session}

def get_week(client, week_start: str):
    resp = client.get(f"/api/schedule?week={week_start}")
    assert resp.status_code == 200, resp.text
    return resp.json()

def events_for_session(events, session_id):
    return [e for e in events if e["session_id"] == session_id]

def db_exceptions():
    with SessionLocal() as db:
        return list(db.scalars(select(SessionException).order_by(SessionException.id)))


def test_move_ok(admin_client):
    w = make_world(admin_client)
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "moved",
            "new_date": "2026-10-19",
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
            "comment": "перенос",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["type"] == "moved"

    events = get_week(admin_client, "2026-10-19")
    same = events_for_session(events, w["session"]["id"])
    assert len(same) == 1
    assert same[0]["status"] == "moved"
    assert same[0]["date"] == "2026-10-19"
    assert same[0]["start_time"] == "12:00"

@pytest.mark.xfail(reason="find_conflicts не вызывается в admin.py - перенос в занятую " \
                            "аудиторию сейчас сохраняется (дефект)", strict=True)
def test_move_room_conflict_409(admin_client):
    w = make_world(admin_client)
    add_extra_world(admin_client, weekday=1, start="12:00", end="13:00", 
                    room_id=w["room"]["id"], name="Other")
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "moved",
            "new_date": "2026-10-19",
            "new_start_time": "12:00", 
            "new_end_time": "12:30",
            "new_room_id": w["room"]["id"],
            "comment": "",
        },
    )
    assert resp.status_code == 409, resp.text
    assert db_exceptions() == []


@pytest.mark.xfail(reason="find_conflicts не вызывается в admin.py - конфликт "
                            "руководителя сейчас не ловится (дефект)", strict=True)
def test_move_leader_conflict_409(admin_client):
    w = make_world(admin_client)
    add_extra_world(admin_client, weekday=1, start="12:00", end="13:00",
                    leader_id=w["leader"]["id"], name="Otherleader")
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "moved",
            "new_date": "2026-10-19",
            "new_start_time": "12:00", 
            "new_end_time": "12:30",
            "new_room_id": w["room"]["id"],
            "comment": "",
        },
    )
    assert resp.status_code == 409, resp.text
    assert db_exceptions() == []

def test_move_adjacent_intervals_allowed(admin_client):
    w = make_world(admin_client)
    add_extra_world(admin_client, weekday=1, start="11:00", end="12:00",
                    room_id=w["room"]["id"], name="Adj")
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "moved",
            "new_date": "2026-10-19",
            "new_start_time": "12:00", 
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
            "comment": "",
        },
    )
    assert resp.status_code == 201, resp.text


def test_move_between_weeks(admin_client):
    w = make_world(admin_client)
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "moved",
            "new_date": "2026-10-26",
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
            "comment": "через неделю",
        },
    )
    assert resp.status_code == 201, resp.text

    src = get_week(admin_client, "2026-10-19")
    assert events_for_session(src, w["session"]["id"]) == []

    dst = get_week(admin_client, "2026-10-26")
    same = events_for_session(dst, w["session"]["id"])
    moved = [e for e in same if e["original_date"] == "2026-10-19"]
    assert len(moved) == 1
    assert moved[0]["status"] == "moved"
    assert moved[0]["date"] == "2026-10-26"
    assert moved[0]["start_time"] == "12:00"
    regular = [e for e in same if e["original_date"] == "2026-10-26"]
    assert len(regular) == 1
    assert regular[0]["status"] == "scheduled"


def test_move_cross_month(admin_client):
    w = make_world(admin_client)
    resp = admin_client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-26",
            "type": "moved",
            "new_date": "2026-11-02",
            "new_start_time": "12:00", 
            "new_end_time": "13:00",
            "new_room_id": w["room"]["id"],
            "comment": "",
        },
    )
    assert resp.status_code == 201, resp.text
    src = get_week(admin_client, "2026-10-26")
    assert events_for_session(src, w["session"]["id"]) == []
    dst = get_week(admin_client, "2026-11-02")
    same = events_for_session(dst, w["session"]["id"])
    moved = [e for e in same if e["original_date"] == "2026-10-26"]
    assert len(moved) == 1
    assert moved[0]["status"] == "moved"
    assert moved[0]["date"] == "2026-11-02"
    regular = [e for e in same if e["original_date"] == "2026-11-02"]
    assert len(regular) == 1
    assert regular[0]["status"] == "scheduled"


def test_patch_move_ok(admin_client):
    w = make_world(admin_client)
    move = _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": w["room"]["id"],
        "comment": "",
    })
    resp = admin_client.patch(
        f"/api/admin/exceptions/{move['id']}",
        json={"new_start_time": "14:00", "new_end_time": "15:00",
              "comment": "сдвинули"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_start_time"] == "14:00"
    assert body["new_end_time"] == "15:00"
    assert body["comment"] == "сдвинули"

    with SessionLocal() as db:
        row = db.get(SessionException, move["id"])
        assert row.new_start_time == "14:00"
        assert row.new_end_time == "15:00"

    events = get_week(admin_client, "2026-10-19")
    same = events_for_session(events, w["session"]["id"])
    assert len(same) == 1
    assert same[0]["start_time"] == "14:00"


@pytest.mark.xfail(reason="find_conflicts не вызывается при PATCH - конфликт " 
                            "не отклоняется, старое значение перезаписывается (дефект)", 
                            strict=True)
def test_patch_move_conflict_keeps_old(admin_client):
    w = make_world(admin_client)
    move = _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": w["room"]["id"],
        "comment": "",
    })
    add_extra_world(admin_client, weekday=1, start="14:00", end="15:00", 
                    room_id=w["room"]["id"], name="Blocker")
    resp = admin_client.patch(
        f"/api/admin/exceptions/{move['id']}",
        json={"new_start_time": "14:30", "new_end_time": "14:45"},
    )
    assert resp.status_code == 409, resp.text
    with SessionLocal() as db:
        row = db.get(SessionException, move["id"])
        assert row.new_start_time == "12:00"
        assert row.new_end_time == "13:00"

def test_patch_move_not_conflict_with_itself(admin_client):
    w = make_world(admin_client)
    move = _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": w["room"]["id"],
        "comment": "",
    })
    resp = admin_client.patch(
        f"/api/admin/exceptions/{move['id']}",
        json={"comment": "только коммент"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["comment"] == "только коммент"


def test_delete_move_restores_regular(admin_client):
    w = make_world(admin_client)
    move =  _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": w["room"]["id"],
        "comment": "",
    })
    assert admin_client.delete(
        f"/api/admin/exceptions/{move['id']}"
    ).status_code == 204

    with SessionLocal() as db:
        assert db.get(SessionException, move["id"]) is None

    src = get_week(admin_client, "2026-10-19")
    same = events_for_session(src, w["session"]["id"])
    assert len(same) == 1
    assert same[0]["status"] == "scheduled"
    assert same[0]["date"] == "2026-10-19"
    assert same[0]["start_time"] == "10:00"


def test_cancellation_lifecycle(admin_client):
    w = make_world(admin_client)
    canc =  _post(admin_client, "/api/admin/exceptions/cancellations", {
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "cancelled",
        "comment": "праздник",
    })

    week = get_week(admin_client, "2026-10-19")
    same = events_for_session(week, w["session"]["id"])
    assert len(same) == 1
    assert same[0]["status"] == "cancelled"
    assert same[0]["comment"] == "праздник"

    next_week = get_week(admin_client, "2026-10-26")
    nxt = events_for_session(next_week, w["session"]["id"])
    assert len(nxt) == 1
    assert nxt[0]["status"] == "scheduled"

    other = add_extra_world(admin_client, weekday=2, start="15:00", end="16:00", name="Untouched")
    week2 = get_week(admin_client, "2026-10-19")
    assert len(events_for_session(week2, other["session"]["id"])) == 1

    assert admin_client.delete(
        f"/api/admin/exceptions/{canc['id']}"
    ).status_code == 204
    week3 = get_week(admin_client, "2026-10-19")
    same3 = events_for_session(week3, w["session"]["id"])
    assert len(same3) == 1
    assert same3[0]["status"] == "scheduled"


def test_unknown_session_404(admin_client):
    resp = admin_client.post(
        "/api/admin/exceptions/moves", 
        json={
        "session_id": 99999,
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": 1,
        "comment": "",
        },
    )
    assert resp.status_code == 404

def test_unknown_room_404(admin_client):
    w = make_world(admin_client)
    resp = admin_client.post(
        "/api/admin/exceptions/moves", 
        json={
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "12:00",
        "new_end_time": "13:00",
        "new_room_id": 99999,
        "comment": "",
        },
    )
    assert resp.status_code == 404

def test_invalid_interval_422(admin_client):
    w = make_world(admin_client)
    resp = admin_client.post(
        "/api/admin/exceptions/moves", 
        json={
        "session_id": w["session"]["id"],
        "original_date": "2026-10-19",
        "type": "moved",
        "new_date": "2026-10-19",
        "new_start_time": "13:00",
        "new_end_time": "12:00",
        "new_room_id": w["room"]["id"],
        "comment": "",
        },
    )
    assert resp.status_code == 422
    assert db_exceptions() == []

def test_duplicate_exception_409(admin_client):
    w = make_world(admin_client)
    _post(admin_client, "/api/admin/exceptions/cancellations", {
    "session_id": w["session"]["id"],
    "original_date": "2026-10-19",
    "type": "cancelled",
    "comment": "",
    })
    resp = admin_client.post(
        "/api/admin/exceptions/cancellations",
        json={
            "session_id": w["session"]["id"],
            "original_date": "2026-10-19",
            "type": "cancelled",
            "comment": "dup",
        },
    )
    assert resp.status_code == 409
    assert len(db_exceptions()) == 1

def test_patch_unknown_exception_404(admin_client):
    assert admin_client.patch(
        "/api/admin/exceptions/99999",
        json={"comment": "x"},
    ).status_code == 404

def test_delete_unknown_exception_404(admin_client):
    assert admin_client.delete(
        "/api/admin/exceptions/99999"
    ).status_code == 404

def test_unauthorized_exception_operations(client):
    assert client.get("/api/admin/exceptions").status_code == 401
    assert client.post("/api/admin/exceptions/cancellations", json={}).status_code == 401
    assert client.post("/api/admin/exceptions/moves", json={}).status_code == 401
    assert client.patch("/api/admin/exceptions/1", json={}).status_code == 401
    assert client.delete("/api/admin/exceptions/1").status_code == 401
