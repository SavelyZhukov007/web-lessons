from datetime import date
import hashlib
import pytest
from sqlalchemy import select
from backend.app.database import Base, SessionLocal
from backend.app.models.category import Category
from backend.app.models.club import Club
from backend.app.models.leader import Leader
from backend.app.models.room import Room
from backend.app.models.session import ClubSession
from backend.app.models.session_exception import SessionException


@pytest.fixture
def calendar_data():
    with SessionLocal() as db:
        category = Category(name="Программирование", color="#2563eb")
        leader = Leader(name="Иван Иванов")
        room = Room(name="101", building="Главный", capacity=20)
        new_room = Room(name="202", building="Главный", capacity=20)
        db.add_all([category, leader, room, new_room])
        db.flush()
        clubs = [
            Club(
                name=name,
                category_id=category.id,
                leader_id=leader.id,
                is_active=active,
            )
            for name, active in [
                ("Python, практика; старт", True),
                ("Другой кружок", True),
                ("Скрытый кружок", False),
                ("Пустой кружок", True),
            ]
        ]
        db.add_all(clubs)
        db.flush()
        sessions = [
            ClubSession(
                club_id=clubs[index].id,
                room_id=room.id,
                weekday=day,
                start_time=start,
                end_time=end,
            )
            for index, day, start, end in [
                (0, 1, "10:00", "11:00"),
                (0, 2, "11:00", "12:00"),
                (0, 3, "14:00", "15:00"),
                (1, 1, "09:00", "10:00"),
                (2, 1, "08:00", "09:00"),
            ]
        ]
        db.add_all(sessions)
        db.flush()
        cancellation = SessionException(
            session_id=sessions[1].id,
            original_date="2026-10-20",
            type="cancelled",
            comment="Занятие отменено",
        )
        move = SessionException(
            session_id=sessions[2].id,
            original_date="2026-10-21",
            type="moved",
            new_date="2026-10-23",
            new_start_time="15:00",
            new_end_time="16:00",
            new_room_id=new_room.id,
            comment="Перенос на пятницу",
        )
        db.add_all([cancellation, move])
        db.commit()
        return {
            "club": clubs[0].id,
            "other": clubs[1].id,
            "hidden": clubs[2].id,
            "empty": clubs[3].id,
            "move": move.id,
            "moved_session": sessions[2].id,
        }


def download(client, club_id, week="2026-10-19"):
    return client.get(f"/api/clubs/{club_id}/calendar.ics", params={"week": week})


def unfolded(response):
    return response.content.decode("utf-8").replace("\r\n ", "")


def snapshot():
    with SessionLocal() as db:
        return {
            table.name: db.execute(select(table)).all()
            for table in Base.metadata.sorted_tables
        }


def test_download_calendar(client, calendar_data, tmp_path):
    response = download(client, calendar_data["club"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    filename = f'club-{calendar_data["club"]}-2026-10-19.ics'
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{filename}"'
    )
    assert response.headers["cache-control"] == "no-store"
    raw = response.content
    assert raw.startswith(b"BEGIN:VCALENDAR\r\n")
    assert raw.endswith(b"END:VCALENDAR\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert all(len(line) <= 75 for line in raw.split(b"\r\n"))
    text = unfolded(response)
    assert text.count("BEGIN:VEVENT") == 2
    assert r"SUMMARY:Python\, практика\; старт" in text
    assert "Руководитель: Иван Иванов" in text
    assert "DTSTART;TZID=Europe/Moscow:20261019T100000" in text
    assert "DTEND;TZID=Europe/Moscow:20261019T110000" in text
    assert "Другой кружок" not in text
    assert "Скрытый кружок" not in text
    output = tmp_path / "lesson-calendar.ics"
    output.write_bytes(raw)
    print(f"Файл для демонстрации: {output}")
