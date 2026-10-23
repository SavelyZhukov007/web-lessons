from copy import deepcopy
from datetime import date, time

import pytest

from backend.app.services.schedule_conflicts import (
    ProposedChange,
    ScheduleConflictService,
)


@pytest.fixture
def service():
    return ScheduleConflictService(db=None)


@pytest.fixture
def schedule_data():
    return {
        "categories": [
            {
                "id": 1,
                "name": "Технические",
                "color": "#ffffff",
            }
        ],
        "leaders": [
            {
                "id": 1,
                "name": "Иван Иванов",
            },
            {
                "id": 2,
                "name": "Пётр Петров",
            },
        ],
        "rooms": [
            {
                "id": 1,
                "name": "101",
            },
            {
                "id": 2,
                "name": "102",
            },
        ],
        "clubs": [
            {
                "id": 1,
                "name": "Робототехника",
                "category_id": 1,
                "leader_id": 1,
                "is_active": True,
            },
            {
                "id": 2,
                "name": "Программирование",
                "category_id": 1,
                "leader_id": 2,
                "is_active": True,
            },
        ],
        "sessions": [
            {
                "id": 10,
                "club_id": 1,
                "room_id": 1,
                "weekday": 1,
                "start_time": time(10, 0),
                "end_time": time(11, 0),
            },
            {
                "id": 20,
                "club_id": 2,
                "room_id": 2,
                "weekday": 2,
                "start_time": time(12, 0),
                "end_time": time(13, 0),
            },
        ],
        "session_exceptions": [],
    }


def mock_data(service, monkeypatch, data):
    monkeypatch.setattr(
        service,
        "_load_schedule_data",
        lambda: deepcopy(data),
    )


# ---------------------------------------------------------
# _apply_proposed_change
# ---------------------------------------------------------


def test_update_session_does_not_change_original_data(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="update_session",
        entity_id=10,
        payload={
            "room_id": 2,
            "start_time": time(14, 0),
        },
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    assert result["sessions"][0]["room_id"] == 2
    assert result["sessions"][0]["start_time"] == time(14, 0)

    # deepcopy должен сохранить исходные данные
    assert schedule_data["sessions"][0]["room_id"] == 1
    assert schedule_data["sessions"][0]["start_time"] == time(10, 0)


def test_create_session(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_session",
        entity_id=30,
        payload={
            "club_id": 1,
            "room_id": 2,
            "weekday": 3,
            "start_time": time(15, 0),
            "end_time": time(16, 0),
        },
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    assert len(result["sessions"]) == 3

    session = result["sessions"][-1]

    assert session["id"] == 30
    assert session["club_id"] == 1
    assert session["room_id"] == 2


def test_create_cancel(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_cancel",
        entity_id=None,
        payload={
            "session_id": 10,
            "original_date": "2026-10-19",
            "comment": "Отмена",
        },
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    exception = result["session_exceptions"][0]

    assert exception["session_id"] == 10
    assert exception["type"] == "cancelled"
    assert exception["original_date"] == "2026-10-19"
    assert exception["new_date"] is None


def test_create_move(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-19",
            "new_room_id": 1,
            "new_start_time": time(10, 30),
            "new_end_time": time(11, 30),
        },
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    exception = result["session_exceptions"][0]

    assert exception["session_id"] == 20
    assert exception["type"] == "moved"
    assert exception["new_date"] == "2026-10-19"
    assert exception["new_room_id"] == 1


def test_delete_exception(
    service,
    schedule_data,
):
    schedule_data["session_exceptions"].append(
        {
            "id": 100,
            "session_id": 10,
            "original_date": "2026-10-19",
            "type": "cancelled",
            "comment": "",
            "new_date": None,
            "new_room_id": None,
            "new_start_time": None,
            "new_end_time": None,
        }
    )

    change = ProposedChange(
        operation="delete_exception",
        entity_id=100,
        payload={},
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    assert result["session_exceptions"] == []

    # В исходных данных exception остался
    assert len(schedule_data["session_exceptions"]) == 1


def test_change_leader(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="change_leader",
        entity_id=2,
        payload={
            "leader_id": 1,
        },
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    club = next(
        club
        for club in result["clubs"]
        if club["id"] == 2
    )

    assert club["leader_id"] == 1


def test_activate_club(
    service,
    schedule_data,
):
    schedule_data["clubs"][0]["is_active"] = False

    change = ProposedChange(
        operation="activate_club",
        entity_id=1,
        payload={},
    )

    result = service._apply_proposed_change(
        schedule_data,
        change,
    )

    assert result["clubs"][0]["is_active"] is True
    assert schedule_data["clubs"][0]["is_active"] is False


# ---------------------------------------------------------
# affected weeks
# ---------------------------------------------------------


def test_move_inside_same_week_returns_one_week(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-22",
            "new_room_id": 1,
            "new_start_time": time(10, 0),
            "new_end_time": time(11, 0),
        },
    )

    weeks = service._get_affected_week_starts(
        schedule_data,
        change,
    )

    assert weeks == {
        date(2026, 10, 19),
    }


def test_cross_week_move_returns_two_weeks(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-26",
            "new_room_id": 1,
            "new_start_time": time(10, 0),
            "new_end_time": time(11, 0),
        },
    )

    weeks = service._get_affected_week_starts(
        schedule_data,
        change,
    )

    assert weeks == {
        date(2026, 10, 19),
        date(2026, 10, 26),
    }


def test_delete_moved_exception_returns_both_weeks(
    service,
    schedule_data,
):
    schedule_data["session_exceptions"].append(
        {
            "id": 100,
            "session_id": 20,
            "original_date": "2026-10-20",
            "type": "moved",
            "comment": "",
            "new_date": "2026-10-26",
            "new_room_id": 1,
            "new_start_time": time(10, 0),
            "new_end_time": time(11, 0),
        }
    )

    change = ProposedChange(
        operation="delete_exception",
        entity_id=100,
        payload={},
    )

    weeks = service._get_affected_week_starts(
        schedule_data,
        change,
    )

    assert weeks == {
        date(2026, 10, 19),
        date(2026, 10, 26),
    }


# ---------------------------------------------------------
# candidates
# ---------------------------------------------------------


def test_update_session_candidate(
    service,
    schedule_data,
):
    events = [
        {
            "event_id": "10:2026-10-19",
            "session_id": 10,
            "club_id": 1,
            "status": "scheduled",
        },
        {
            "event_id": "20:2026-10-20",
            "session_id": 20,
            "club_id": 2,
            "status": "scheduled",
        },
    ]

    change = ProposedChange(
        operation="update_session",
        entity_id=10,
        payload={},
    )

    candidates = service._get_candidates(
        events,
        change,
        schedule_data,
    )

    assert len(candidates) == 1
    assert candidates[0]["session_id"] == 10


def test_change_leader_returns_all_club_events(
    service,
    schedule_data,
):
    events = [
        {
            "event_id": "10:1",
            "session_id": 10,
            "club_id": 1,
            "status": "scheduled",
        },
        {
            "event_id": "11:1",
            "session_id": 11,
            "club_id": 1,
            "status": "scheduled",
        },
        {
            "event_id": "20:1",
            "session_id": 20,
            "club_id": 2,
            "status": "scheduled",
        },
    ]

    change = ProposedChange(
        operation="change_leader",
        entity_id=1,
        payload={
            "leader_id": 2,
        },
    )

    candidates = service._get_candidates(
        events,
        change,
        schedule_data,
    )

    assert len(candidates) == 2

    assert all(
        event["club_id"] == 1
        for event in candidates
    )


def test_cancel_has_no_candidate(
    service,
    schedule_data,
):
    change = ProposedChange(
        operation="create_cancel",
        entity_id=None,
        payload={
            "session_id": 10,
            "original_date": "2026-10-19",
        },
    )

    candidates = service._get_candidates(
        [],
        change,
        schedule_data,
    )

    assert candidates == []


# ---------------------------------------------------------
# Полная цепочка check_proposed_state
# ---------------------------------------------------------


def test_move_creates_room_conflict(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Session 10:
    Monday 10:00-11:00, room 1

    Session 20 переносим:
    Monday 10:30-11:30, room 1

    Должен быть конфликт по комнате.
    """

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-19",
            "new_room_id": 1,
            "new_start_time": time(10, 30),
            "new_end_time": time(11, 30),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts

    assert any(
        "room" in conflict["reasons"]
        for conflict in conflicts
    )


def test_move_creates_leader_conflict(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Оба кружка имеют одного руководителя.
    Аудитории разные.

    Время пересекается.
    Должен быть конфликт только по leader.
    """

    schedule_data["clubs"][1]["leader_id"] = 1

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-19",
            "new_room_id": 2,
            "new_start_time": time(10, 30),
            "new_end_time": time(11, 30),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts

    assert any(
        "leader" in conflict["reasons"]
        for conflict in conflicts
    )


def test_touching_intervals_do_not_conflict(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Первое занятие:
    10:00-11:00

    Перенос:
    11:00-12:00

    Границы касаются, но пересечения нет.
    """

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-19",
            "new_room_id": 1,
            "new_start_time": time(11, 0),
            "new_end_time": time(12, 0),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts == []


def test_cancelled_event_frees_room(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Session 10 на 19 октября отменена.

    Session 20 переносим на её время и комнату.

    Конфликта быть не должно.
    """

    schedule_data["session_exceptions"].append(
        {
            "id": 100,
            "session_id": 10,
            "original_date": "2026-10-19",
            "type": "cancelled",
            "comment": "",
            "new_date": None,
            "new_room_id": None,
            "new_start_time": None,
            "new_end_time": None,
        }
    )

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-19",
            "new_room_id": 1,
            "new_start_time": time(10, 0),
            "new_end_time": time(11, 0),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts == []


def test_cross_week_move_detects_conflict(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Session 10 повторяется каждый понедельник 10:00-11:00.

    Session 20 переносим с 20 октября
    на следующий понедельник 26 октября,
    10:30-11:30 в ту же аудиторию.

    Сервис должен построить обе недели
    и найти конфликт 26 октября.
    """

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-26",
            "new_room_id": 1,
            "new_start_time": time(10, 30),
            "new_end_time": time(11, 30),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts

    assert any(
        "room" in conflict["reasons"]
        for conflict in conflicts
    )


def test_candidate_does_not_conflict_with_itself(
    service,
    schedule_data,
    monkeypatch,
):
    """
    Перенос ни с кем не пересекается.

    Проверяем, что событие не считается
    конфликтующим само с собой.
    """

    mock_data(
        service,
        monkeypatch,
        schedule_data,
    )

    change = ProposedChange(
        operation="create_move",
        entity_id=None,
        payload={
            "session_id": 20,
            "original_date": "2026-10-20",
            "new_date": "2026-10-21",
            "new_room_id": 2,
            "new_start_time": time(15, 0),
            "new_end_time": time(16, 0),
        },
    )

    conflicts = service.check_proposed_state(change)

    assert conflicts == []
