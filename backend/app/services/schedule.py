"""Фёдор: формирование недели. Без API и БД; результат соответствует ScheduleEvent."""
from __future__ import annotations

from datetime import date, timedelta


def build_week(week_start: date, data: dict) -> list[dict]:
    if week_start.isoweekday() != 1:
        raise ValueError(
            f"Неверный день недели, должен быть Monday(Понедельник), а не {week_start.strftime('%A')}"
        )

    week_end = week_start + timedelta(days=6)
    active_clubs = {club["id"]: club for club in data["clubs"] if club["is_active"]}
    categories = {category["id"]: category for category in data["categories"]}
    leaders = {leader["id"]: leader for leader in data["leaders"]}
    rooms = {room["id"]: room for room in data["rooms"]}
    sessions = {session["id"]: session for session in data["sessions"]}
    exceptions = {
        (item["session_id"], item["original_date"]): item
        for item in data["session_exceptions"]
    }

    events: list[dict] = []

    for session in data["sessions"]:
        club = active_clubs.get(session["club_id"])
        if club is None:
            continue

        original_date = week_start + timedelta(days=session["weekday"] - 1)
        original_date_text = original_date.isoformat()
        exception = exceptions.get((session["id"], original_date_text))
        payload = _base_event_payload(session, club, categories, leaders)

        if exception is None:
            events.append(
                {
                    **payload,
                    "event_id": f"{session['id']}:{original_date_text}",
                    "room_id": session["room_id"],
                    "room_name": rooms[session["room_id"]]["name"],
                    "date": original_date_text,
                    "start_time": session["start_time"],
                    "end_time": session["end_time"],
                    "status": "scheduled",
                    "original_date": original_date_text,
                    "comment": "",
                }
            )
            continue

        if exception["type"] == "cancelled":
            events.append(
                {
                    **payload,
                    "event_id": f"{session['id']}:{original_date_text}",
                    "room_id": session["room_id"],
                    "room_name": rooms[session["room_id"]]["name"],
                    "date": original_date_text,
                    "start_time": session["start_time"],
                    "end_time": session["end_time"],
                    "status": "cancelled",
                    "original_date": original_date_text,
                    "comment": exception["comment"],
                }
            )
            continue

        moved_date = date.fromisoformat(exception["new_date"])
        if week_start <= moved_date <= week_end:
            events.append(
                {
                    **payload,
                    "event_id": f"{session['id']}:{original_date_text}",
                    "room_id": exception["new_room_id"],
                    "room_name": rooms[exception["new_room_id"]]["name"],
                    "date": exception["new_date"],
                    "start_time": exception["new_start_time"],
                    "end_time": exception["new_end_time"],
                    "status": "moved",
                    "original_date": original_date_text,
                    "comment": exception["comment"],
                }
            )

    for exception in data["session_exceptions"]:
        if exception["type"] != "moved":
            continue
        moved_date = date.fromisoformat(exception["new_date"])
        original_date = date.fromisoformat(exception["original_date"])
        if not week_start <= moved_date <= week_end or week_start <= original_date <= week_end:
            continue

        session = sessions.get(exception["session_id"])
        if session is None:
            continue

        club = active_clubs.get(session["club_id"])
        if club is None:
            continue

        payload = _base_event_payload(session, club, categories, leaders)
        events.append(
            {
                **payload,
                "event_id": f"{session['id']}:{exception['original_date']}",
                "room_id": exception["new_room_id"],
                "room_name": rooms[exception["new_room_id"]]["name"],
                "date": exception["new_date"],
                "start_time": exception["new_start_time"],
                "end_time": exception["new_end_time"],
                "status": "moved",
                "original_date": exception["original_date"],
                "comment": exception["comment"],
            }
        )

    events.sort(key=lambda item: (item["date"], item["start_time"], item["club_name"]))
    return events


def _base_event_payload(
    session: dict,
    club: dict,
    categories: dict,
    leaders: dict,
) -> dict:
    category = categories[club["category_id"]]
    leader = leaders[club["leader_id"]]
    return {
        "session_id": session["id"],
        "club_id": club["id"],
        "club_name": club["name"],
        "category_id": category["id"],
        "category_name": category["name"],
        "category_color": category["color"],
        "leader_id": leader["id"],
        "leader_name": leader["name"],
    }
