from datetime import date
import pytest
from backend.app.services.schedule import build_week


@pytest.fixture
def sample_data():
    return {
        "meta": {
            "fictional": True,
            "description": "Тестовый набор недели (12.10.2026 - 18.10.2026)",
        },
        "categories": [
            {"id": 1, "name": "Программирование", "color": "#2563eb"},
            {"id": 2, "name": "Робототехника", "color": "#dc2626"},
            {"id": 3, "name": "Дизайн", "color": "#16a34a"},
        ],
        "leaders": [
            {
                "id": 1,
                "name": "Иван Иванов",
                "position": "Старший преподаватель",
                "contact": "abc@test.com",
            },
            {
                "id": 2,
                "name": "Анна Смирнова",
                "position": "Инженер",
                "contact": "def@test.com",
            },
            {
                "id": 3,
                "name": "Алексей Петров",
                "position": "Дизайнер",
                "contact": "ghi@test.com",
            },
        ],
        "rooms": [
            {"id": 1, "name": "101", "building": "Главный", "capacity": 20},
            {"id": 2, "name": "202", "building": "Главный", "capacity": 15},
            {
                "id": 3,
                "name": "Лаборатория 303",
                "building": "Технопарк",
                "capacity": 10,
            },
        ],
        "clubs": [
            {
                "id": 1,
                "name": "Python для начинающих",
                "category_id": 1,
                "leader_id": 1,
                "is_active": True,
            },
            {
                "id": 2,
                "name": "Неактивный кружок старой школы",
                "category_id": 1,
                "leader_id": 1,
                "is_active": False,
            },
            {
                "id": 3,
                "name": "Робототехника++",
                "category_id": 2,
                "leader_id": 2,
                "is_active": True,
            },
            {
                "id": 4,
                "name": "Веб-дизайн и UI/UX",
                "category_id": 3,
                "leader_id": 3,
                "is_active": True,
            },
        ],
        "sessions": [
            # кружок 1 (Пн) -> 2026-10-12
            {
                "id": 1,
                "club_id": 1,
                "room_id": 1,
                "weekday": 1,
                "start_time": "15:00",
                "end_time": "16:00",
            },
            # кружок 1 (Ср) -> 2026-10-14
            {
                "id": 2,
                "club_id": 1,
                "room_id": 2,
                "weekday": 3,
                "start_time": "10:00",
                "end_time": "11:30",
            },
            # кружок 3 (Вт) ->  2026-10-13
            {
                "id": 3,
                "club_id": 3,
                "room_id": 3,
                "weekday": 2,
                "start_time": "14:00",
                "end_time": "15:30",
            },
            # кружок 3 (Чт) -> 2026-10-15
            {
                "id": 4,
                "club_id": 3,
                "room_id": 3,
                "weekday": 4,
                "start_time": "14:00",
                "end_time": "15:30",
            },
            # кружок 4 (Пт) -> 2026-10-16
            {
                "id": 5,
                "club_id": 4,
                "room_id": 1,
                "weekday": 5,
                "start_time": "16:00",
                "end_time": "18:00",
            },
            # кружок 2 (Ср) -> Неактивный
            {
                "id": 6,
                "club_id": 2,
                "room_id": 2,
                "weekday": 3,
                "start_time": "12:00",
                "end_time": "13:00",
            },
        ],
        "session_exceptions": [
            # Отмена кружка 3 во Вт 2026-10-13
            {
                "session_id": 3,
                "original_date": "2026-10-13",
                "type": "cancelled",
                "comment": "",
            },
            # Перенос внутри недели: session 1 (2026-10-12) -> (2026-10-17) в другую комнату (2)
            {
                "session_id": 1,
                "original_date": "2026-10-12",
                "type": "moved",
                "new_date": "2026-10-17",
                "new_start_time": "11:00",
                "new_end_time": "12:00",
                "new_room_id": 2,
                "comment": "",
            },
            # Перенос из недели: session 5 (2026-10-16) -> (2026-10-21) в другую комнату (1)
            {
                "session_id": 5,
                "original_date": "2026-10-16",
                "type": "moved",
                "new_date": "2026-10-21",
                "new_start_time": "16:00",
                "new_end_time": "18:00",
                "new_room_id": 1,
                "comment": "",
            },
            # Перенос из другой недели в эту: session 2 (2026-10-07) -> (2026-10-15) в другую комнату (3)
            {
                "session_id": 2,
                "original_date": "2026-10-07",
                "type": "moved",
                "new_date": "2026-10-15",
                "new_start_time": "12:00",
                "new_end_time": "13:30",
                "new_room_id": 3,
                "comment": "",
            },
        ],
    }


def test_build_week_invalid_start_day(sample_data):
    """Проверка ValueError"""
    tuesday = date(2026, 10, 13)
    with pytest.raises(ValueError, match="Неверный день недели"):
        build_week(tuesday, sample_data)


def test_build_week_normal(sample_data):
    """Обычная генерация без "session_exceptions"."""
    sample_data["session_exceptions"] = []
    monday = date(2026, 10, 12)
    events = build_week(monday, sample_data)

    assert len(events) == 5

    assert events[0]["date"] == "2026-10-12"
    assert events[0]["status"] == "scheduled"
    assert events[0]["club_name"] == "Python для начинающих"

    assert events[1]["date"] == "2026-10-13"
    assert events[1]["status"] == "scheduled"
    assert events[1]["club_name"] == "Робототехника++"

    assert events[2]["date"] == "2026-10-14"
    assert events[2]["status"] == "scheduled"
    assert events[2]["club_name"] == "Python для начинающих"

    assert events[3]["date"] == "2026-10-15"
    assert events[3]["status"] == "scheduled"
    assert events[3]["club_name"] == "Робототехника++"

    assert events[4]["date"] == "2026-10-16"
    assert events[4]["status"] == "scheduled"
    assert events[4]["club_name"] == "Веб-дизайн и UI/UX"


def test_build_week_cancellation(sample_data):
    """Проверка отмены занятия."""
    monday = date(2026, 10, 12)
    events = build_week(monday, sample_data)

    cancelled_event = next(e for e in events if e["date"] == "2026-10-13")

    assert cancelled_event["status"] == "cancelled"
    assert cancelled_event["comment"] == ""

    assert cancelled_event["start_time"] == "14:00"
    assert cancelled_event["end_time"] == "15:30"


def test_build_week_same_week_move(sample_data):
    """Перенос внутри недели."""
    monday = date(2026, 10, 12)
    events = build_week(monday, sample_data)

    # Исходный слот понедельника должен отсутствовать, а субботний — появиться со статусом moved
    dates = [e["date"] for e in events]
    assert "2026-10-12" not in dates
    assert "2026-10-17" in dates

    moved_event = next(e for e in events if e["date"] == "2026-10-17")

    assert moved_event["status"] == "moved"
    assert moved_event["original_date"] == "2026-10-12"
    assert moved_event["room_id"] == 2
    assert moved_event["room_name"] == "202"
    assert moved_event["start_time"] == "11:00"


def test_build_week_cross_week_move(sample_data):
    """Межнедельные переносы."""
    monday = date(2026, 10, 12)
    events = build_week(monday, sample_data)

    # Перенос из недели в другую: 2026-10-16 -> следующая неделя
    assert not any(e["original_date"] == "2026-10-16" for e in events)

    # Перенос в неделю из другой: 2026-10-07 -> 2026-10-15
    moved_in_event = next(
        (e for e in events if e["original_date"] == "2026-10-07"), None
    )
    assert moved_in_event is not None
    assert moved_in_event["date"] == "2026-10-15"
    assert moved_in_event["status"] == "moved"
    assert moved_in_event["room_name"] == "Лаборатория 303"
