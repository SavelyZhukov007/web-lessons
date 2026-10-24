"""QA-01: HTTP-тесты конфликтов расписания для занятий и кружков (создание/правка занятия, смена руководителя,
активация скрытого кружка) — позитивный и конфликтный путь для каждой мутации."""
from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


def _second_club(client, w, name="Второй", leader_id=None, active=True):
    return _post(client, "/api/admin/clubs", {
        "name": name, "description": "", "category_id": w["category"]["id"],
        "leader_id": leader_id or w["leader"]["id"], "is_active": active,
    })


def _session(client, club, room, weekday, start, end):
    return client.post("/api/admin/sessions", json={"club_id": club["id"], "room_id": room["id"], "weekday": weekday, "start_time": start, "end_time": end})


def test_create_session_room_conflict_409_and_adjacent_ok(admin_client):
    w = make_world(admin_client, weekday=2, start="10:00", end="11:00")
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    club2 = _second_club(admin_client, w, leader_id=other_leader["id"])
    r = _session(admin_client, club2, w["room"], 2, "10:30", "11:30")
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["code"] and body["message"] and body["conflicts"]
    assert _session(admin_client, club2, w["room"], 2, "11:00", "12:00").status_code == 201  # впритык — не конфликт


def test_create_session_leader_conflict_409(admin_client):
    w = make_world(admin_client, weekday=3, start="10:00", end="11:00")
    club2 = _second_club(admin_client, w)  # тот же руководитель
    room2 = _post(admin_client, "/api/admin/rooms", {"name": "202", "building": "Главный", "capacity": 10})
    assert _session(admin_client, club2, room2, 3, "10:30", "11:30").status_code == 409
    assert _session(admin_client, club2, room2, 4, "10:30", "11:30").status_code == 201  # другой день


def test_patch_session_conflict_409_keeps_old_value_and_ok_path(admin_client):
    w = make_world(admin_client, weekday=1, start="10:00", end="11:00")
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    club2 = _second_club(admin_client, w, leader_id=other_leader["id"])
    second = _session(admin_client, club2, w["room"], 1, "12:00", "13:00").json()
    bad = admin_client.patch(f"/api/admin/sessions/{second['id']}", json={"start_time": "10:30", "end_time": "11:30"})
    assert bad.status_code == 409
    still = next(s for s in admin_client.get("/api/admin/sessions").json() if s["id"] == second["id"])
    assert (still["start_time"], still["end_time"]) == ("12:00", "13:00")
    ok = admin_client.patch(f"/api/admin/sessions/{second['id']}", json={"start_time": "11:00", "end_time": "12:00"})
    assert ok.status_code == 200 and ok.json()["start_time"] == "11:00"
    same = admin_client.patch(f"/api/admin/sessions/{w['session']['id']}", json={"end_time": "10:45"})  # не конфликтует сам с собой
    assert same.status_code == 200


def test_change_club_leader_conflict_409_and_ok_path(admin_client):
    w = make_world(admin_client, weekday=5, start="10:00", end="11:00")
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    room2 = _post(admin_client, "/api/admin/rooms", {"name": "303", "building": "Главный", "capacity": 10})
    club2 = _second_club(admin_client, w, leader_id=other_leader["id"])
    assert _session(admin_client, club2, room2, 5, "10:30", "11:30").status_code == 201
    bad = admin_client.patch(f"/api/admin/clubs/{club2['id']}", json={"leader_id": w["leader"]["id"]})
    assert bad.status_code == 409
    assert next(c for c in admin_client.get("/api/admin/clubs").json() if c["id"] == club2["id"])["leader_id"] == other_leader["id"]
    third = _post(admin_client, "/api/admin/leaders", {"name": "Третий", "position": "", "contact": ""})
    assert admin_client.patch(f"/api/admin/clubs/{club2['id']}", json={"leader_id": third["id"]}).status_code == 200


def test_activating_hidden_club_with_conflict_409_and_ok_when_free(admin_client):
    w = make_world(admin_client, weekday=1, start="10:00", end="11:00")
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    hidden = _second_club(admin_client, w, leader_id=other_leader["id"], active=False)
    assert _session(admin_client, hidden, w["room"], 1, "10:30", "11:30").status_code == 201  # скрытый кружок не конфликтует
    assert admin_client.patch(f"/api/admin/clubs/{hidden['id']}", json={"is_active": True}).status_code == 409
    assert admin_client.delete(f"/api/admin/sessions/{_session(admin_client, hidden, w['room'], 6, '10:00', '11:00').json()['id']}").status_code in (200, 204)
    hidden2 = _second_club(admin_client, w, name="Свободный", leader_id=other_leader["id"], active=False)
    assert admin_client.patch(f"/api/admin/clubs/{hidden2['id']}", json={"is_active": True}).status_code == 200
