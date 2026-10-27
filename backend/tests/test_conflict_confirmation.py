from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401
from .test_import_drafts import docx
from .test_schedule_v2 import dataset


def test_confirmation_is_required_and_bound_to_current_conflicts(admin_client):
    world = make_world(admin_client, weekday=2, start="15:30", end="17:00")
    club = _post(admin_client, "/api/admin/clubs", {
        "name": "Совместное занятие", "category_id": world["category"]["id"],
        "leader_id": world["leader"]["id"],
    })
    payload = {"club_id": club["id"], "room_id": world["room"]["id"],
               "weekday": 2, "start_time": "15:50", "end_time": "17:20"}
    warning = admin_client.post("/api/admin/sessions", json=payload)
    assert warning.status_code == 409
    detail = warning.json()["detail"]
    assert set(detail["conflicts"][0]["reasons"]) == {"room", "leader"}
    token = detail["confirmation_token"]
    assert len(admin_client.get("/api/admin/sessions").json()) == 1

    # Approval for one interval must not approve another interval.
    stale = admin_client.post("/api/admin/sessions", json={**payload, "end_time": "17:30"},
                              headers={"X-Confirmed-Conflicts": token})
    assert stale.status_code == 409
    assert stale.json()["detail"]["confirmation_token"] != token
    result = admin_client.post("/api/admin/sessions", json=payload,
                               headers={"X-Confirmed-Conflicts": token})
    assert result.status_code == 201, result.text
    assert len(admin_client.get("/api/admin/sessions").json()) == 2


def test_draft_import_can_confirm_conflicts_without_partial_save(admin_client):
    world = make_world(admin_client, weekday=2, start="15:30", end="17:00")
    rows = [["День", "Кружок", "Руководитель", "Время", "Аудитория"],
            ["Вторник", "Новое занятие", "Иван Иванов", "15:50–17:20", "101"]]
    draft = _post(admin_client, "/api/admin/imports", {"filename": "schedule.docx", "content_base64": docx(rows)})
    choice = {"row": 2, "action": "create", "category_id": world["category"]["id"],
              "leader_id": world["leader"]["id"], "room_ids": [world["room"]["id"]]}
    assert admin_client.put(f"/api/admin/imports/{draft['id']}/decisions", json={"decisions": [choice]}).status_code == 200
    path = f"/api/admin/imports/{draft['id']}/publish"
    warning = admin_client.post(path)
    assert warning.status_code == 409, warning.text
    assert len(admin_client.get("/api/admin/sessions").json()) == 1
    token = warning.json()["detail"]["confirmation_token"]
    published = admin_client.post(path, headers={"X-Confirmed-Conflicts": token})
    assert published.status_code == 200, published.text
    assert len(admin_client.get("/api/admin/sessions").json()) == 2


def test_robotics_and_databases_touch_without_conflict(admin_client):
    world = make_world(admin_client, weekday=2, start="14:00", end="16:00")
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Щербаков", "position": "", "contact": ""})
    other_club = _post(admin_client, "/api/admin/clubs", {"name": "Администрирование баз данных", "category_id": world["category"]["id"], "leader_id": other_leader["id"]})
    result = admin_client.post("/api/admin/sessions", json={"club_id": other_club["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "16:00", "end_time": "17:20"})
    assert result.status_code == 201, result.text


def test_move_conflict_can_be_confirmed_without_bypassing_validation(admin_client):
    world = make_world(admin_client, weekday=2, start="15:30", end="17:00")
    other_room = _post(admin_client, "/api/admin/rooms", {"name": "Зал 2", "building": "", "capacity": 20})
    other_leader = _post(admin_client, "/api/admin/leaders", {"name": "Другой", "position": "", "contact": ""})
    club = _post(admin_client, "/api/admin/clubs", {"name": "Второй", "category_id": world["category"]["id"], "leader_id": other_leader["id"]})
    lesson = _post(admin_client, "/api/admin/sessions", {"club_id": club["id"], "room_id": other_room["id"], "weekday": 2, "start_time": "15:30", "end_time": "17:00"})
    move = {"session_id": lesson["id"], "original_date": "2026-11-03", "new_date": "2026-11-03", "new_start_time": "15:50", "new_end_time": "17:20", "new_room_id": world["room"]["id"]}
    warning = admin_client.post("/api/admin/exceptions/moves", json=move)
    assert warning.status_code == 409, warning.text
    token = warning.json()["detail"]["confirmation_token"]
    result = admin_client.post("/api/admin/exceptions/moves", json=move, headers={"X-Confirmed-Conflicts": token})
    assert result.status_code == 201, result.text
    # This is a separate rule: confirmation cannot create a second exception.
    duplicate = admin_client.post("/api/admin/exceptions/moves", json=move, headers={"X-Confirmed-Conflicts": token})
    assert duplicate.status_code == 409


def test_json_import_can_confirm_conflicts(admin_client):
    make_world(admin_client, weekday=1)
    data = dataset()
    data["leaders"].append({"full_name": "Иван Иванов"})
    data["clubs"][1]["leaders"] = ["Иван Иванов"]
    data["clubs"][1]["sessions"][0].update({"weekday": 1, "start": "10:00", "end": "11:00"})
    path = "/api/admin/import/publish"
    warning = admin_client.post(path, json=data)
    assert warning.status_code == 409, warning.text
    token = warning.json()["detail"]["confirmation_token"]
    result = admin_client.post(path, json=data, headers={"X-Confirmed-Conflicts": token})
    assert result.status_code == 200, result.text


def test_restoring_holiday_can_be_confirmed(admin_client):
    world = make_world(admin_client)
    period = _post(admin_client, "/api/admin/periods", {"name": "Период", "start_date": "2026-11-02", "end_date": "2026-11-30", "even_week_start": "2026-11-02"})
    _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "period_id": period["id"], "repeat": "even"})
    holiday = _post(admin_client, f"/api/admin/periods/{period['id']}/days-off", {"date": "2026-11-03", "reason": "Каникулы"})
    _post(admin_client, "/api/admin/sessions", {"club_id": world["club"]["id"], "room_id": world["room"]["id"], "weekday": 2, "start_time": "11:00", "end_time": "12:00", "one_off_date": "2026-11-03"})
    path = f"/api/admin/periods/{period['id']}/days-off/{holiday['id']}"
    warning = admin_client.delete(path)
    assert warning.status_code == 409, warning.text
    result = admin_client.delete(path, headers={"X-Confirmed-Conflicts": warning.json()["detail"]["confirmation_token"]})
    assert result.status_code == 204, result.text
