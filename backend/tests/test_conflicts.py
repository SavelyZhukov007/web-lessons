from datetime import date, time

from backend.app.services.conflicts import (
    find_conflicts,
    intervals_overlap,
)


def test_find_conflicts_same_room():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 21),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 1,
            "leader_id": 9,
            "status": "active",
        }
    ]

    assert find_conflicts(candidate, events) == [
        {"event_id": "e1", "reasons": ["room"]}
    ]


def test_find_conflicts_same_leader():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 21),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 2,
            "leader_id": 7,
            "status": "active",
        }
    ]

    assert find_conflicts(candidate, events) == [
        {"event_id": "e1", "reasons": ["leader"]}
    ]


def test_intervals_adjacent():
    assert (
        intervals_overlap(
            time(10, 0),
            time(11, 0),
            time(11, 0),
            time(12, 0),
        )
        is False
    )


def test_find_conflicts_different_dates():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 22),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 1,
            "leader_id": 7,
            "status": "active",
        }
    ]

    assert find_conflicts(candidate, events) == []


def test_find_conflicts_cancelled_event():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 21),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 1,
            "leader_id": 7,
            "status": "cancelled",
        }
    ]

    assert find_conflicts(candidate, events) == []


def test_find_conflicts_excludes_edited_event():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 21),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 1,
            "leader_id": 9,
            "status": "active",
        },
        {
            "event_id": "e2",
            "date": date(2026, 10, 21),
            "start_time": time(11, 30),
            "end_time": time(12, 30),
            "room_id": 1,
            "leader_id": 10,
            "status": "active",
        },
    ]

    assert find_conflicts(
        candidate,
        events,
        exclude_event_id="e1",
    ) == [{"event_id": "e2", "reasons": ["room"]}]


def test_find_conflicts_same_room_and_leader():
    candidate = {
        "date": date(2026, 10, 21),
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "room_id": 1,
        "leader_id": 7,
    }

    events = [
        {
            "event_id": "e1",
            "date": date(2026, 10, 21),
            "start_time": time(11, 0),
            "end_time": time(13, 0),
            "room_id": 1,
            "leader_id": 7,
            "status": "active",
        }
    ]

    assert find_conflicts(candidate, events) == [
        {"event_id": "e1", "reasons": ["room", "leader"]}
    ]
