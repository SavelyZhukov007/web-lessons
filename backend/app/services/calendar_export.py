from datetime import date

from tools.calendar_export.generate_ics import generate_ics

from .schedule import build_week


def build_club_calendar(
    *, week_start: date, data: dict, club_id: int, club_name: str
) -> str:
    events = build_week(week_start, data)
    club_events = [
        event for event in events if event["club_id"] == club_id
    ]
    return generate_ics({"club_name": club_name, "events": club_events})
