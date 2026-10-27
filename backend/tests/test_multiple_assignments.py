from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


def test_conflicts_check_all_leaders_and_rooms(admin_client):
    world = make_world(admin_client, weekday=1, start="10:00", end="11:00")
    leader2 = _post(admin_client, "/api/admin/leaders", {"name": "Второй", "position": "", "contact": ""})
    room2 = _post(admin_client, "/api/admin/rooms", {"name": "102", "building": "", "capacity": None})
    club2 = _post(admin_client, "/api/admin/clubs", {"name": "Второй кружок", "description": "", "category_id": world["category"]["id"], "leader_id": leader2["id"]})
    updated = admin_client.patch(f"/api/admin/sessions/{world['session']['id']}", json={"leader_ids": [world["leader"]["id"], leader2["id"]], "room_ids": [world["room"]["id"], room2["id"]]})
    assert updated.status_code == 200, updated.text
    proposed = {"club_id": club2["id"], "room_id": room2["id"], "weekday": 1, "start_time": "10:00", "end_time": "11:00"}
    rejected = admin_client.post("/api/admin/sessions", json=proposed)
    assert rejected.status_code == 409, rejected.text
    reasons = rejected.json()["detail"]["conflicts"][0]["reasons"]
    assert set(reasons) == {"room", "leader"}
    events = admin_client.get("/api/schedule?week=2026-11-02").json()
    event = next(e for e in events if e["session_id"] == world["session"]["id"])
    assert set(event["leader_ids"]) == {world["leader"]["id"], leader2["id"]}
    assert set(event["room_ids"]) == {world["room"]["id"], room2["id"]}
    assert admin_client.delete(f"/api/admin/leaders/{leader2['id']}").status_code == 409
    assert admin_client.delete(f"/api/admin/rooms/{room2['id']}").status_code == 409


def test_remote_location_does_not_block_unrelated_teacher(admin_client):
    world = make_world(admin_client)
    remote = _post(admin_client, "/api/admin/rooms", {"name": "Дистанционно", "is_remote": True})
    other = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    club = _post(admin_client, "/api/admin/clubs", {"name": "Онлайн", "category_id": world["category"]["id"], "leader_id": other["id"]})
    for hour in ["13:00", "13:00"]:
        response = admin_client.post("/api/admin/sessions", json={"club_id": club["id"], "room_id": remote["id"], "weekday": 2, "start_time": hour, "end_time": "14:00"})
        if hour == "13:00" and response.status_code == 201:
            club = _post(admin_client, "/api/admin/clubs", {"name": "Онлайн 2", "category_id": world["category"]["id"], "leader_id": world["leader"]["id"]})
        else:
            assert response.status_code == 201, response.text
