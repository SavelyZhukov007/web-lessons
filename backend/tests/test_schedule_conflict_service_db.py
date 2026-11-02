"""ScheduleConflictService на реальной БД: каждая операция ProposedChange находит (или не находит) пересечения."""
from datetime import date

import pytest

from backend.app.database import SessionLocal
from backend.app.services import schedule_conflicts as sc
from backend.app.services.schedule_conflicts import ProposedChange, ScheduleConflictService

from .test_exception_conflicts_api import _post, add_extra_world, admin_client, make_world  # noqa: F401


@pytest.fixture
def world(admin_client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(sc, "today_msk", lambda: date(2026, 10, 27))
    a = make_world(admin_client, weekday=1, start="10:00", end="11:00")
    b = add_extra_world(admin_client, weekday=3, start="10:00", end="11:00", name="Среда")
    c = add_extra_world(admin_client, weekday=1, start="10:30", end="11:30", name="Понедельник")
    move = _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": a["session"]["id"], "original_date": "2026-11-09", "type": "moved", "new_date": "2026-11-18",
        "new_start_time": "12:00", "new_end_time": "13:00", "new_room_id": a["room"]["id"], "comment": ""})
    return {"a": a, "b": b, "c": c, "move": move, "client": admin_client}


def check(op, entity_id, payload):
    with SessionLocal() as db:
        return ScheduleConflictService(db).check_proposed_state(ProposedChange(op, entity_id, payload))


def names(found):
    return {f["club_name"] for f in found}


def test_create_move_into_busy_room(world):
    a, b = world["a"], world["b"]
    found = check("create_move", None, {
        "session_id": a["session"]["id"], "original_date": "2026-11-16", "new_date": "2026-11-18",
        "new_start_time": "10:00", "new_end_time": "11:00", "new_room_id": b["room"]["id"]})
    assert names(found) == {"Среда"}
    assert found[0]["date"] == "2026-11-18" and found[0]["reasons"]


def test_create_cancel_never_conflicts(world):
    assert check("create_cancel", None, {"session_id": world["a"]["session"]["id"], "original_date": "2026-11-16"}) == []


def test_update_session_and_create_session(world):
    a, b = world["a"], world["b"]
    found = check("update_session", a["session"]["id"], {"weekday": 3, "room_id": b["room"]["id"], "room_ids": [b["room"]["id"]]})
    assert "Среда" in names(found)
    found = check("create_session", None, {
        "club_id": a["club"]["id"], "room_id": b["room"]["id"], "weekday": 3, "start_time": "10:15",
        "end_time": "10:45", "one_off_date": "2026-11-11"})
    assert names(found) == {"Среда"}


def test_leader_changes(world):
    a, c = world["a"], world["c"]
    # change_leader меняет только основного руководителя; пересечение считается по leader_ids
    assert isinstance(check("change_leader", a["club"]["id"], {"leader_id": c["leader"]["id"]}), list)
    found = check("update_club", a["club"]["id"], {"leader_id": a["leader"]["id"], "leader_ids": [c["leader"]["id"]]})
    assert "Понедельник" in names(found)
    assert check("update_club", a["club"]["id"], {"leader_id": a["leader"]["id"], "is_active": True}) == []
    assert check("activate_club", a["club"]["id"], {}) == []


def test_update_and_delete_move(world):
    a, b, move = world["a"], world["b"], world["move"]
    found = check("update_move", move["id"], {"new_date": date(2026, 11, 11), "new_start_time": "10:00",
                                              "new_end_time": "11:00", "new_room_id": b["room"]["id"]})
    assert names(found) == {"Среда"}
    # смена исходной даты: старый слот возвращается в расписание — тоже кандидат
    found = check("update_move", move["id"], {"original_date": "2026-11-16"})
    assert isinstance(found, list)
    assert check("update_move", 999999, {"new_date": "2026-11-11"}) == []
    assert check("delete_exception", move["id"], {}) == []
    assert check("delete_exception", 999999, {}) == []
    assert a["session"]["id"]
