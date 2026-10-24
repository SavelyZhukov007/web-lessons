from sqlalchemy import select

from backend.app.auth import hash_password
from backend.app.database import SessionLocal
from backend.app.models.admin import Admin


def create_admin(login="admin", password="Password123"):
    with SessionLocal() as db:
        db.add(Admin(login=login, password_hash=hash_password(password)))
        db.commit()


def login_admin(client):
    response = client.post(
        "/api/admin/login",
        json={"login": "Admin", "password": "Password123"},
    )
    assert response.status_code == 200
    assert response.json()["admin"]["login"] == "admin"
    assert "admin_session=" in response.headers["set-cookie"]


def test_admin_login_logout_and_protection(client):
    create_admin()

    assert client.get("/api/admin/status").status_code == 401
    assert client.get("/api/admin/categories").status_code == 401
    assert (
        client.post(
            "/api/admin/login", json={"login": "admin", "password": "bad-pass"}
        ).status_code
        == 401
    )

    login_admin(client)

    assert client.get("/api/admin/status").status_code == 200
    assert client.get("/api/admin/categories").json() == []

    assert client.post("/api/admin/logout").status_code == 204
    assert client.get("/api/admin/status").status_code == 401


def test_admin_crud_and_public_schedule(client):
    create_admin()
    login_admin(client)

    category = client.post(
        "/api/admin/categories",
        json={"name": "Программирование", "color": "#2563eb"},
    ).json()
    leader = client.post(
        "/api/admin/leaders",
        json={
            "name": "Иван Иванов",
            "position": "Преподаватель",
            "contact": "ivan@test.local",
        },
    ).json()
    room = client.post(
        "/api/admin/rooms",
        json={"name": "101", "building": "Главный корпус", "capacity": 20},
    ).json()
    second_room = client.post(
        "/api/admin/rooms",
        json={"name": "202", "building": "Главный корпус", "capacity": 12},
    ).json()
    club = client.post(
        "/api/admin/clubs",
        json={
            "name": "Python для начинающих",
            "description": "Базовый курс",
            "category_id": category["id"],
            "leader_id": leader["id"],
            "is_active": True,
        },
    ).json()
    session = client.post(
        "/api/admin/sessions",
        json={
            "club_id": club["id"],
            "room_id": room["id"],
            "weekday": 2,
            "start_time": "15:00",
            "end_time": "16:00",
        },
    ).json()
    cancellation = client.post(
        "/api/admin/exceptions/cancellations",
        json={
            "session_id": session["id"],
            "original_date": "2026-10-13",
            "type": "cancelled",
            "comment": "Праздничный день",
        },
    ).json()
    move = client.post(
        "/api/admin/exceptions/moves",
        json={
            "session_id": session["id"],
            "original_date": "2026-10-20",
            "type": "moved",
            "new_date": "2026-10-22",
            "new_start_time": "17:00",
            "new_end_time": "18:00",
            "new_room_id": second_room["id"],
            "comment": "Перенос на вечер",
        },
    ).json()

    detail = client.get(f"/api/clubs/{club['id']}").json()
    assert detail["id"] == club["id"]
    assert detail["sessions"][0]["room"]["id"] == room["id"]
    assert len(detail["upcoming_exceptions"]) == 2

    current_week = client.get("/api/schedule?week=2026-10-12").json()
    cancelled = next(
        item for item in current_week if item["original_date"] == "2026-10-13"
    )
    assert cancelled["status"] == "cancelled"

    moved_week = client.get("/api/schedule?week=2026-10-19").json()
    moved = next(item for item in moved_week if item["original_date"] == "2026-10-20")
    assert moved["status"] == "moved"
    assert moved["room_id"] == second_room["id"]

    updated_room = client.patch(
        f"/api/admin/rooms/{second_room['id']}",
        json={"capacity": 18},
    ).json()
    assert updated_room["capacity"] == 18

    updated_move = client.patch(
        f"/api/admin/exceptions/{move['id']}",
        json={"comment": "Перенос из-за мероприятия", "new_end_time": "18:30"},
    ).json()
    assert updated_move["comment"] == "Перенос из-за мероприятия"
    assert updated_move["new_end_time"] == "18:30"

    assert (
        client.patch(
            f"/api/admin/clubs/{club['id']}",
            json={"is_active": False},
        ).json()["is_active"]
        is False
    )
    assert client.get("/api/clubs").json() == []

    assert (
        client.patch(
            f"/api/admin/clubs/{club['id']}",
            json={"is_active": True},
        ).json()["is_active"]
        is True
    )
    assert len(client.get("/api/clubs").json()) == 1

    assert client.delete(f"/api/admin/exceptions/{move['id']}").status_code == 204
    assert (
        client.delete(f"/api/admin/exceptions/{cancellation['id']}").status_code == 204
    )
    assert client.delete(f"/api/admin/sessions/{session['id']}").status_code == 204
    assert client.delete(f"/api/admin/clubs/{club['id']}").status_code == 204
    assert client.delete(f"/api/admin/rooms/{second_room['id']}").status_code == 204
    assert client.delete(f"/api/admin/rooms/{room['id']}").status_code == 204
    assert client.delete(f"/api/admin/leaders/{leader['id']}").status_code == 204
    assert client.delete(f"/api/admin/categories/{category['id']}").status_code == 204

    with SessionLocal() as db:
        assert db.scalar(select(Admin).where(Admin.login == "admin")) is not None


def test_admin_login_rate_limit(client):
    create_admin(login="rateadmin", password="Password123")

    for _ in range(5):
        response = client.post(
            "/api/admin/login",
            json={"login": "rateadmin", "password": "wrong-password"},
        )
        assert response.status_code == 401

    response = client.post(
        "/api/admin/login",
        json={"login": "rateadmin", "password": "wrong-password"},
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert "Слишком много неудачных попыток" in response.json()["detail"]
