"""Единое правило существования исходного занятия на конкретную дату."""
from datetime import date, timedelta


def original_occurs(session: dict, day: date, period: dict | None = None, holidays=()) -> bool:
    if day.isoweekday() != session["weekday"]:
        return False
    once = session.get("one_off_date")
    if once and day.isoformat() != str(once):
        return False
    if period:
        if not period["start_date"] <= day.isoformat() <= period["end_date"]:
            return False
        if day.isoformat() in holidays:
            return False
        repeat = session.get("repeat", "weekly")
        if repeat in ("even", "odd"):
            monday = day - timedelta(days=day.weekday())
            anchor = date.fromisoformat(period["even_week_start"])
            even = ((monday - anchor).days // 7) % 2 == 0
            if even != (repeat == "even"):
                return False
    return True


def occurrences_for_range(start: date, end: date, data: dict, club_id: int | None = None) -> list[dict]:
    """Вернуть реальные события за диапазон с применёнными отменами и переносами."""
    from .schedule import build_week

    week = start - timedelta(days=start.weekday())
    events = {}
    while week <= end:
        for event in build_week(week, data):
            if (club_id is None or event["club_id"] == club_id) and start.isoformat() <= event["date"] <= end.isoformat():
                events[event["event_id"]] = event
        week += timedelta(days=7)
    return sorted(events.values(), key=lambda event: (event["date"], event["start_time"], event["club_name"]))
