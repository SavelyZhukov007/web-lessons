"""Phase 2 F: параллельные занятия — несколько кружков в одно время в РАЗНЫХ аудиториях у РАЗНЫХ руководителей разрешены;
та же аудитория или тот же руководитель — 409; отмена/перенос одного не трогает соседние."""
from .test_exception_conflicts_api import _post, admin_client, get_week, make_world  # noqa: F401
from .test_session_club_conflicts_api import _second_club, _session

MON = "2026-10-19"  # понедельник; вторник = 2026-10-20


def _parallel(client):
    w = make_world(client, weekday=2, start="15:00", end="16:30")
    leader2 = _post(client, "/api/admin/leaders", {"name": "Петрова Анна", "position": "", "contact": ""})
    leader3 = _post(client, "/api/admin/leaders", {"name": "Сидоров Олег", "position": "", "contact": ""})
    room2 = _post(client, "/api/admin/rooms", {"name": "202", "building": "Главный", "capacity": 15})
    room3 = _post(client, "/api/admin/rooms", {"name": "Актовый зал", "building": "Главный", "capacity": 80})
    c2 = _second_club(client, w, name="Театр", leader_id=leader2["id"])
    c3 = _second_club(client, w, name="Волейбол", leader_id=leader3["id"])
    s2 = _session(client, c2, room2, 2, "15:00", "16:30")
    s3 = _session(client, c3, room3, 2, "15:30", "17:00")  # частично пересекается — тоже можно
    assert s2.status_code == 201 and s3.status_code == 201, (s2.text, s3.text)
    return w, s2.json(), s3.json(), room2, leader2


def test_parallel_in_different_rooms_allowed_and_listed(admin_client):
    w, s2, s3, *_ = _parallel(admin_client)
    tue = [e for e in get_week(admin_client, MON) if e["date"] == "2026-10-20"]
    assert {e["session_id"] for e in tue} == {w["session"]["id"], s2["id"], s3["id"]}
    assert all(e["status"] == "scheduled" for e in tue)
    assert len({e["room_id"] for e in tue}) == 3


def test_parallel_same_room_or_leader_still_409(admin_client):
    w, s2, s3, room2, leader2 = _parallel(admin_client)
    other = _post(admin_client, "/api/admin/leaders", {"name": "Новиков", "position": "", "contact": ""})
    c4 = _second_club(admin_client, w, name="Шахматы", leader_id=other["id"])
    assert _session(admin_client, c4, room2, 2, "16:00", "17:00").status_code == 409  # аудитория 202 занята
    room4 = _post(admin_client, "/api/admin/rooms", {"name": "404", "building": "Главный", "capacity": 10})
    c5 = _second_club(admin_client, w, name="Хор", leader_id=leader2["id"])
    assert _session(admin_client, c5, room4, 2, "15:10", "15:50").status_code == 409  # руководитель занят
    assert _session(admin_client, c4, room4, 2, "15:10", "15:50").status_code == 201  # четвёртый параллельный — можно


def test_cancel_one_parallel_keeps_others(admin_client):
    w, s2, s3, *_ = _parallel(admin_client)
    _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": s2["id"], "original_date": "2026-10-20", "comment": "Болезнь"})
    tue = {e["session_id"]: e for e in get_week(admin_client, MON) if e["date"] == "2026-10-20"}
    assert tue[s2["id"]]["status"] == "cancelled" and tue[s2["id"]]["comment"] == "Болезнь"
    assert tue[w["session"]["id"]]["status"] == "scheduled" and tue[s3["id"]]["status"] == "scheduled"


def test_move_into_parallel_slot_other_room_ok_same_room_409(admin_client):
    w, s2, s3, room2, _ = _parallel(admin_client)
    other = _post(admin_client, "/api/admin/leaders", {"name": "Орлова", "position": "", "contact": ""})
    room5 = _post(admin_client, "/api/admin/rooms", {"name": "505", "building": "Главный", "capacity": 10})
    c6 = _second_club(admin_client, w, name="Фото", leader_id=other["id"])
    s6 = _session(admin_client, c6, room5, 4, "15:00", "16:30").json()
    base = {"session_id": s6["id"], "original_date": "2026-10-22", "new_date": "2026-10-20", "new_start_time": "15:00", "new_end_time": "16:30"}
    bad = admin_client.post("/api/admin/exceptions/moves", json={**base, "new_room_id": room2["id"]})
    assert bad.status_code == 409
    ok = admin_client.post("/api/admin/exceptions/moves", json={**base, "new_room_id": room5["id"]})
    assert ok.status_code == 201, ok.text
    tue = [e for e in get_week(admin_client, MON) if e["date"] == "2026-10-20" and e["start_time"] == "15:00"]
    assert len(tue) == 3 and any(e["status"] == "moved" for e in tue)
