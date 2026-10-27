"""Разовое занятие не меняет постоянное расписание и проверяется на свою дату."""
from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


def another_club(client, world):
    teacher = _post(client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    return _post(client, "/api/admin/clubs", {"name": "Разовый", "description": "", "category_id": world["category"]["id"], "leader_id": teacher["id"], "is_active": True})


def test_one_off_uses_cancelled_room_only_on_that_date(admin_client):
    world = make_world(admin_client, weekday=1, start="15:00", end="16:00")
    club = another_club(admin_client, world)
    cancelled = _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": world["session"]["id"], "original_date": "2026-11-02"})
    payload = {"club_id": club["id"], "room_id": world["room"]["id"], "weekday": 1, "start_time": "15:00", "end_time": "16:00", "one_off_date": "2026-11-02"}
    one = admin_client.post("/api/admin/sessions", json=payload)
    assert one.status_code == 201, one.text
    assert one.json()["one_off_date"] == "2026-11-02"
    first = admin_client.get("/api/schedule?week=2026-11-02").json()
    assert any(e["club_id"] == club["id"] and e["status"] == "scheduled" for e in first)
    assert any(e["session_id"] == world["session"]["id"] and e["status"] == "cancelled" for e in first)
    next_week = admin_client.get("/api/schedule?week=2026-11-09").json()
    assert all(e["club_id"] != club["id"] for e in next_week)
    assert any(e["session_id"] == world["session"]["id"] and e["status"] == "scheduled" for e in next_week)
    assert admin_client.post("/api/admin/sessions", json={**payload, "one_off_date": "2026-11-09"}).status_code == 409
    assert admin_client.post("/api/admin/sessions", json={k: v for k, v in payload.items() if k != "one_off_date"}).status_code == 409
    # Восстановление физры в занятую аудиторию тоже запрещено.
    assert admin_client.delete(f"/api/admin/exceptions/{cancelled['id']}").status_code == 409


def test_duplicate_cancel_and_move_explain_existing_exception(admin_client):
    world = make_world(admin_client)
    base = {"session_id": world["session"]["id"], "original_date": "2026-11-02"}
    _post(admin_client, "/api/admin/exceptions/cancellations", base)
    again = admin_client.post("/api/admin/exceptions/cancellations", json=base)
    assert again.status_code == 409 and "уже отменено" in again.json()["detail"]
    moved = admin_client.post("/api/admin/exceptions/moves", json={**base, "new_date": "2026-11-03", "new_start_time": "12:00", "new_end_time": "13:00", "new_room_id": world["room"]["id"]})
    assert moved.status_code == 409 and "уже отменено" in moved.json()["detail"]
    assert len(admin_client.get("/api/admin/exceptions").json()) == 1


def test_invalid_one_off_date_and_conflict_in_future_are_rejected(admin_client):
    world = make_world(admin_client)
    club = another_club(admin_client, world)
    payload = {"club_id": club["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "10:00", "end_time": "11:00", "one_off_date": "2026-11-02"}
    assert admin_client.post("/api/admin/sessions", json=payload).status_code == 422
    payload.update(weekday=1, one_off_date="2026-11-09")
    assert admin_client.post("/api/admin/sessions", json=payload).status_code == 409
