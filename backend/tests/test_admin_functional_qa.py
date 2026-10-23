import pytest

from backend.app.auth import hash_password
from backend.app.database import SessionLocal
from backend.app.models.admin import Admin
from backend.app.schemas.category import CategoryRead
from backend.app.schemas.club import ClubRead
from backend.app.schemas.leader import LeaderRead
from backend.app.schemas.room import RoomRead
from backend.app.schemas.session import SessionRead
from backend.app.schemas.session_exception import SessionExceptionRead


@pytest.fixture
def admin_client(client):
    with SessionLocal() as db:
        db.add(Admin(login="qa_admin", password_hash=hash_password("TestPassword123")))
        db.commit()
    response = client.post("/api/admin/login", json={"login": "qa_admin", "password": "TestPassword123"})
    assert response.status_code == 200
    return client


def assert_object(response, status, schema, expected):
    assert response.status_code == status, response.text
    body = response.json()
    schema.model_validate(body, strict=True)
    assert isinstance(body["id"], int) and body["id"] > 0
    assert all(body[field] == value for field, value in expected.items())
    return body["id"]


def create_category(client):
    payload = {"name": "QA направление", "color": "#2563eb"}
    return assert_object(client.post("/api/admin/categories", json=payload), 201, CategoryRead, payload)


def create_leader(client):
    payload = {"name": "Тестовый руководитель", "position": "Преподаватель", "contact": "qa@example.test"}
    return assert_object(client.post("/api/admin/leaders", json=payload), 201, LeaderRead, payload)


def create_room(client, name="QA-101"):
    payload = {"name": name, "building": "Тестовый корпус", "capacity": 20}
    return assert_object(client.post("/api/admin/rooms", json=payload), 201, RoomRead, payload)


def create_club(client, category_id, leader_id):
    payload = {
        "name": "QA кружок", "description": "Проверка админки",
        "category_id": category_id, "leader_id": leader_id, "is_active": True,
    }
    return assert_object(client.post("/api/admin/clubs", json=payload), 201, ClubRead, payload)


def create_schedule(client):
    category_id, leader_id, room_id = create_category(client), create_leader(client), create_room(client)
    club_id = create_club(client, category_id, leader_id)
    payload = {"club_id": club_id, "room_id": room_id, "weekday": 2, "start_time": "15:00", "end_time": "16:00"}
    session_id = assert_object(client.post("/api/admin/sessions", json=payload), 201, SessionRead, payload)
    return category_id, leader_id, room_id, club_id, session_id


@pytest.mark.parametrize(
    ("resource", "payload", "schema", "patch"),
    [
        ("categories", {"name": "Робототехника", "color": "#2563eb"}, CategoryRead, {"name": "Программирование"}),
        ("leaders", {"name": "Ирина Тестова", "position": "Педагог", "contact": "qa@example.test"}, LeaderRead, {"position": "Наставник"}),
        ("rooms", {"name": "201", "building": "Учебный", "capacity": 20}, RoomRead, {"capacity": 25}),
    ],
)
def test_reference_crud(admin_client, resource, payload, schema, patch):
    """POST → GET списка → PATCH → GET списка → DELETE → GET списка."""
    client = admin_client
    path = f"/api/admin/{resource}"
    item_id = assert_object(client.post(path, json=payload), 201, schema, payload)
    listed = client.get(path)
    assert listed.status_code == 200
    item = next(row for row in listed.json() if row["id"] == item_id)
    schema.model_validate(item, strict=True)
    assert all(item[key] == value for key, value in payload.items())

    assert_object(client.patch(f"{path}/{item_id}", json=patch), 200, schema, patch)
    saved = next(row for row in client.get(path).json() if row["id"] == item_id)
    assert all(saved[key] == value for key, value in {**payload, **patch}.items())

    deleted = client.delete(f"{path}/{item_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert all(row["id"] != item_id for row in client.get(path).json())


@pytest.mark.parametrize(
    ("resource", "payload"),
    [
        ("categories", {"name": "", "color": "#2563eb"}),
        ("rooms", {"name": "101", "building": "Учебный", "capacity": 0}),
    ],
)
def test_invalid_reference_is_not_saved(admin_client, resource, payload):
    client = admin_client
    response = client.post(f"/api/admin/{resource}", json=payload)
    assert response.status_code == 422 and response.json()["detail"]
    listed = client.get(f"/api/admin/{resource}")
    assert listed.status_code == 200 and listed.json() == []


def test_duplicate_category_returns_conflict_without_duplicate(admin_client):
    client = admin_client
    create_category(client)
    response = client.post("/api/admin/categories", json={"name": "QA направление", "color": "#2563eb"})
    assert response.status_code == 409 and response.json()["detail"]
    assert len(client.get("/api/admin/categories").json()) == 1


def test_club_hide_and_restore(admin_client):
    client = admin_client
    club_id = create_club(client, create_category(client), create_leader(client))
    assert client.get("/api/clubs").json()[0]["id"] == club_id
    assert_object(client.patch(f"/api/admin/clubs/{club_id}", json={"is_active": False}), 200, ClubRead, {"is_active": False})
    assert client.get("/api/clubs").json() == []
    assert client.get("/api/admin/clubs").json()[0]["id"] == club_id
    assert_object(client.patch(f"/api/admin/clubs/{club_id}", json={"is_active": True}), 200, ClubRead, {"is_active": True})
    assert client.get("/api/clubs").json()[0]["id"] == club_id


def test_club_edit_and_delete(admin_client):
    client = admin_client
    club_id = create_club(client, create_category(client), create_leader(client))
    assert_object(client.patch(f"/api/admin/clubs/{club_id}", json={"name": "QA новое название"}), 200, ClubRead, {"name": "QA новое название"})
    assert client.get("/api/admin/clubs").json()[0]["name"] == "QA новое название"
    deleted = client.delete(f"/api/admin/clubs/{club_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get("/api/admin/clubs").json() == []
    assert client.get("/api/clubs").json() == []


def test_session_edit_and_invalid_time_preserves_saved_value(admin_client):
    client = admin_client
    session_id = create_schedule(client)[4]
    path = f"/api/admin/sessions/{session_id}"
    assert_object(client.patch(path, json={"end_time": "16:30"}), 200, SessionRead, {"end_time": "16:30"})
    invalid = client.patch(path, json={"end_time": "14:00"})
    assert invalid.status_code == 422 and invalid.json()["detail"]
    saved = next(row for row in client.get("/api/admin/sessions").json() if row["id"] == session_id)
    assert saved["end_time"] == "16:30"


def test_session_delete_removes_public_event(admin_client):
    client = admin_client
    session_id = create_schedule(client)[4]
    assert len(client.get("/api/schedule?week=2026-10-19").json()) == 1
    deleted = client.delete(f"/api/admin/sessions/{session_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get("/api/admin/sessions").json() == []
    assert client.get("/api/schedule?week=2026-10-19").json() == []


@pytest.mark.parametrize("resource_index,resource", [(0, "categories"), (1, "leaders"), (2, "rooms")])
def test_linked_reference_cannot_be_deleted(admin_client, resource_index, resource):
    client = admin_client
    ids = create_schedule(client)
    response = client.delete(f"/api/admin/{resource}/{ids[resource_index]}")
    assert response.status_code == 409 and response.json()["detail"]
    assert any(row["id"] == ids[resource_index] for row in client.get(f"/api/admin/{resource}").json())


def test_cancellation_lifecycle(admin_client):
    client = admin_client
    session_id = create_schedule(client)[4]
    payload = {"session_id": session_id, "original_date": "2026-10-20", "type": "cancelled", "comment": "Проверка"}
    exception_id = assert_object(client.post("/api/admin/exceptions/cancellations", json=payload), 201, SessionExceptionRead, payload)
    assert client.get("/api/schedule?week=2026-10-19").json()[0]["status"] == "cancelled"
    assert_object(client.patch(f"/api/admin/exceptions/{exception_id}", json={"comment": "Новая причина"}), 200, SessionExceptionRead, {"comment": "Новая причина"})
    assert client.get("/api/admin/exceptions").json()[0]["comment"] == "Новая причина"
    deleted = client.delete(f"/api/admin/exceptions/{exception_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get("/api/admin/exceptions").json() == []
    assert client.get("/api/schedule?week=2026-10-19").json()[0]["status"] == "scheduled"


def test_duplicate_cancellation_returns_conflict(admin_client):
    client = admin_client
    session_id = create_schedule(client)[4]
    payload = {"session_id": session_id, "original_date": "2026-10-20"}
    assert client.post("/api/admin/exceptions/cancellations", json=payload).status_code == 201
    response = client.post("/api/admin/exceptions/cancellations", json=payload)
    assert response.status_code == 409 and response.json()["detail"]
    assert len(client.get("/api/admin/exceptions").json()) == 1


def test_move_lifecycle_and_invalid_edit(admin_client):
    client = admin_client
    session_id = create_schedule(client)[4]
    new_room_id = create_room(client, "QA-102")
    payload = {
        "session_id": session_id, "original_date": "2026-10-27", "type": "moved",
        "new_date": "2026-10-29", "new_start_time": "17:00",
        "new_end_time": "18:00", "new_room_id": new_room_id, "comment": "Перенос",
    }
    exception_id = assert_object(client.post("/api/admin/exceptions/moves", json=payload), 201, SessionExceptionRead, payload)
    moved = client.get("/api/schedule?week=2026-10-26").json()[0]
    assert (moved["status"], moved["date"], moved["room_id"]) == ("moved", "2026-10-29", new_room_id)
    invalid = client.patch(f"/api/admin/exceptions/{exception_id}", json={"new_end_time": "16:00"})
    assert invalid.status_code == 422 and invalid.json()["detail"]
    assert client.get("/api/admin/exceptions").json()[0]["new_end_time"] == "18:00"
    assert_object(client.patch(f"/api/admin/exceptions/{exception_id}", json={"new_end_time": "18:30"}), 200, SessionExceptionRead, {"new_end_time": "18:30"})
    assert client.get("/api/schedule?week=2026-10-26").json()[0]["end_time"] == "18:30"
    deleted = client.delete(f"/api/admin/exceptions/{exception_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get("/api/admin/exceptions").json() == []
