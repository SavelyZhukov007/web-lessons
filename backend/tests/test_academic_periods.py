from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


def test_alternating_weeks_and_holiday_conflicts(admin_client):
    world = make_world(admin_client, weekday=1, start="09:00", end="10:00")
    period = _post(admin_client, "/api/admin/periods", {"name": "Осень", "start_date": "2026-11-02", "end_date": "2026-12-20", "even_week_start": "2026-11-02"})
    leader = _post(admin_client, "/api/admin/leaders", {"name": "Второй преподаватель", "position": "", "contact": ""})
    club = _post(admin_client, "/api/admin/clubs", {"name": "Кружок B", "description": "", "category_id": world["category"]["id"], "leader_id": leader["id"], "is_active": True})
    base = {"club_id": club["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "period_id": period["id"]}
    even = _post(admin_client, "/api/admin/sessions", {**base, "repeat": "even"})
    odd = _post(admin_client, "/api/admin/sessions", {**base, "repeat": "odd"})
    assert admin_client.post("/api/admin/sessions", json={**base, "repeat": "even"}).status_code == 409
    week = admin_client.get("/api/schedule?week=2026-11-02").json()
    assert any(e["session_id"] == even["id"] for e in week)
    assert not any(e["session_id"] == odd["id"] for e in week)
    week = admin_client.get("/api/schedule?week=2026-11-09").json()
    assert any(e["session_id"] == odd["id"] for e in week)
    assert admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": even["id"], "original_date": "2026-11-10"}).status_code == 409
    _post(admin_client, f"/api/admin/periods/{period['id']}/days-off", {"date": "2026-11-03", "reason": "Каникулы"})
    assert not any(e["session_id"] == even["id"] for e in admin_client.get("/api/schedule?week=2026-11-02").json())
    assert admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": even["id"], "original_date": "2026-11-03"}).status_code == 409


def test_calendar_export_uses_parity_cancellations_and_moves(admin_client):
    world = make_world(admin_client, weekday=1, start="09:00", end="10:00")
    period = _post(admin_client, "/api/admin/periods", {"name": "Период", "start_date": "2026-12-14", "end_date": "2027-01-17", "even_week_start": "2026-12-14"})
    lesson = _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "period_id": period["id"], "repeat": "even"})
    _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": lesson["id"], "original_date": "2026-12-29"})
    _post(admin_client, "/api/admin/exceptions/moves", {"session_id": lesson["id"], "original_date": "2027-01-12", "new_date": "2027-01-13", "new_start_time": "11:00", "new_end_time": "12:00", "new_room_id": world["room"]["id"]})
    response = admin_client.get(f"/api/clubs/{world['club']['id']}/calendar.ics?start=2026-12-14&end=2027-01-17")
    assert response.status_code == 200, response.text
    assert "20261215T110000" in response.text
    assert "20261229T110000" not in response.text
    assert "20270113T110000" in response.text
    assert "20270112T110000" not in response.text
    assert admin_client.get(f"/api/clubs/{world['club']['id']}/calendar.ics?start=2026-01-01&end=2026-12-31").status_code == 422


def test_period_edit_and_move_cannot_invalidate_exceptions(admin_client):
    world = make_world(admin_client)
    data = {"name": "Осень", "start_date": "2026-11-02", "end_date": "2026-11-30", "even_week_start": "2026-11-02"}
    period = _post(admin_client, "/api/admin/periods", data)
    lesson = _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "period_id": period["id"], "repeat": "even"})
    _post(admin_client, f"/api/admin/periods/{period['id']}/days-off", {"date": "2026-11-04", "reason": "Праздник"})
    move = {"session_id": lesson["id"], "original_date": "2026-11-03", "new_date": "2026-11-04", "new_start_time": "11:00", "new_end_time": "12:00", "new_room_id": world["room"]["id"]}
    assert admin_client.post("/api/admin/exceptions/moves", json=move).status_code == 409
    assert admin_client.post("/api/admin/exceptions/moves", json={**move, "new_date": "2026-12-01"}).status_code == 409
    _post(admin_client, "/api/admin/exceptions/cancellations", {"session_id": lesson["id"], "original_date": "2026-11-03"})
    assert admin_client.put(f"/api/admin/periods/{period['id']}", json={**data, "even_week_start": "2026-11-09"}).status_code == 409


def test_holiday_range_and_restore_conflict(admin_client):
    world = make_world(admin_client)
    period = _post(admin_client, "/api/admin/periods", {"name": "Период", "start_date": "2026-11-02", "end_date": "2026-11-30", "even_week_start": "2026-11-02"})
    lesson = _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "period_id": period["id"], "repeat": "even"})
    result = _post(admin_client, f"/api/admin/periods/{period['id']}/days-off/range", {"start_date": "2026-11-03", "end_date": "2026-11-05", "reason": "Каникулы"})
    assert result["added"] == 3
    day = next(d for d in admin_client.get(f"/api/admin/periods/{period['id']}/days-off").json() if d["date"] == "2026-11-03")
    _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "one_off_date": "2026-11-03"})
    assert admin_client.delete(f"/api/admin/periods/{period['id']}/days-off/{day['id']}").status_code == 409
    assert not any(e["session_id"] == lesson["id"] for e in admin_client.get("/api/schedule?week=2026-11-02").json())
