from __future__ import annotations

from datetime import date, timedelta

from .occurrences import original_occurs


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
    periods = {p["id"]: p for p in data.get("periods", [])}
    holidays = {}
    for day in data.get("no_class_days", []):
        holidays.setdefault(day["period_id"], set()).add(day["date"])
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
        if not original_occurs(session, original_date, periods.get(session.get("period_id")), holidays.get(session.get("period_id"), ())):
            continue
        exception = exceptions.get((session["id"], original_date_text))
        payload = _base_event_payload(session, club, categories, leaders)

        if exception is None:
            events.append(
                {
                    **payload,
                    "event_id": f"{session['id']}:{original_date_text}",
                    **_location_payload(session.get("room_ids") or [session["room_id"]], rooms),
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
                    **_location_payload(session.get("room_ids") or [session["room_id"]], rooms),
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
                    **_location_payload([exception["new_room_id"]], rooms),
                    "date": exception["new_date"],
                    "start_time": exception["new_start_time"],
                    "end_time": exception["new_end_time"],
                    "status": "moved",
                    "original_date": original_date_text,
                    "original_start_time": session["start_time"],
                    "original_end_time": session["end_time"],
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
                **_location_payload([exception["new_room_id"]], rooms),
                "date": exception["new_date"],
                "start_time": exception["new_start_time"],
                "end_time": exception["new_end_time"],
                "status": "moved",
                "original_date": exception["original_date"],
                "original_start_time": session["start_time"],
                "original_end_time": session["end_time"],
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
    ids = session.get("leader_ids") or club.get("leader_ids") or [club["leader_id"]]
    leader = leaders[ids[0]]
    return {
        "session_id": session["id"],
        "club_id": club["id"],
        "club_name": club["name"],
        "category_id": category["id"],
        "category_name": category["name"],
        "category_color": category["color"],
        "leader_id": leader["id"],
        "leader_name": leader["name"],
        "leader_ids": ids,
        "leader_names": [leaders[item]["name"] for item in ids],
        "repeat": session.get("repeat", "once" if session.get("one_off_date") else "weekly"),
        "period_id": session.get("period_id"),
    }


def _location_payload(ids: list, rooms: dict) -> dict:
    first = rooms[ids[0]]
    return {"room_id": ids[0], "room_name": first["name"], "room_ids": ids,
            "room_names": [" · ".join(filter(None, [rooms[item]["name"], rooms[item].get("building")])) for item in ids],
            "occupied_room_ids": [item for item in ids if not rooms[item].get("is_remote", False)],
            "is_remote": all(rooms[item].get("is_remote", False) for item in ids)}
