from __future__ import annotations

from .test_exception_conflicts_api import admin_client, make_world  # noqa: F401


def event(client):
    result = client.get("/api/admin/calendar?week=2026-11-09")
    assert result.status_code == 200, result.text
    return result.json()["items"][0]


def body(item, room_id, new_date="2026-11-10"):
    return {
        "event_id": item["event_id"],
        "source_date": item["date"],
        "revision": item["revision"],
        "move": {
            "type": "moved",
            "session_id": item["session_id"],
            "original_date": item["original_date"],
            "new_date": new_date,
            "new_start_time": "12:00",
            "new_end_time": "13:00",
            "new_room_id": room_id,
            "comment": "Тест",
        },
    }


def test_calendar_move_is_one_occurrence_and_second_move_updates_existing_exception(admin_client):
    world = make_world(admin_client)
    original = event(admin_client)
    result = admin_client.post("/api/admin/calendar/move", json=body(original, world["room"]["id"]))
    assert result.status_code == 200, result.text
    moved = event(admin_client)
    assert moved["date"] == "2026-11-10" and moved["exception_id"]
    result = admin_client.post("/api/admin/calendar/move", json=body(moved, world["room"]["id"], "2026-11-11"))
    assert result.status_code == 200, result.text
    assert len(admin_client.get("/api/admin/exceptions").json()) == 1
    assert admin_client.get("/api/admin/sessions").json()[0]["weekday"] == 1


def test_calendar_stale_and_aba_are_rejected(admin_client):
    world = make_world(admin_client)
    original = event(admin_client)
    for end in ["11:10", "11:00"]:
        assert admin_client.patch("/api/admin/sessions/" + str(world["session"]["id"]), json={"end_time": end}).status_code == 200
    assert admin_client.post("/api/admin/calendar/move", json=body(original, world["room"]["id"])).status_code == 409
    assert admin_client.get("/api/admin/exceptions").json() == []


def test_calendar_validates_source_and_conflicts(admin_client):
    world = make_world(admin_client)
    original = event(admin_client)
    invalid = body(original, world["room"]["id"])
    invalid["move"]["session_id"] += 1
    assert admin_client.post("/api/admin/calendar/move", json=invalid).status_code == 422
    assert admin_client.get("/api/admin/calendar?week=2026-11-10").status_code == 422


def test_drag_move_rechecks_conflicts_and_requires_explicit_confirmation(admin_client):
    world = make_world(admin_client)
    other = admin_client.post('/api/admin/sessions', json={'club_id': world['club']['id'], 'room_id': world['room']['id'], 'weekday': 2, 'start_time': '12:00', 'end_time': '13:00'})
    assert other.status_code == 201
    original = next(x for x in admin_client.get('/api/admin/calendar?week=2026-11-09').json()['items'] if x['session_id'] == world['session']['id'])
    payload = body(original, world['room']['id'])
    rejected = admin_client.post('/api/admin/calendar/move', json=payload)
    assert rejected.status_code == 409 and rejected.json()['detail']['confirmation_token']
    assert admin_client.get('/api/admin/exceptions').json() == []
    accepted = admin_client.post('/api/admin/calendar/move', json=payload, headers={'X-Confirmed-Conflicts': rejected.json()['detail']['confirmation_token']})
    assert accepted.status_code == 200, accepted.text
