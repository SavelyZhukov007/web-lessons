"""Экспорт .ics. Все даты — из occurrence_source: по одному VEVENT на реальную дату.

* UID стабилен для occurrence: sha256("session_id:исходная_дата") — тот же, что у
  event_id недели, поэтому перенос заменяет исходное занятие в подписанном календаре;
* перенесённое занятие — отдельный VEVENT на новой дате (с пометкой о переносе);
* отменённые и «ушедшие» (moved_out) даты в файл не попадают;
* никаких RRULE — неучебные дни и чётность недель уже учтены в списке дат.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from tools.calendar_export.generate_ics import _event_lines, _fold_line, _parse_schedule, generate_ics

from . import occurrence_source as occ_src

_HEADER = [
    "BEGIN:VCALENDAR",
    "PRODID:-//Calendar Export Tool//RU",
    "VERSION:2.0",
    "CALSCALE:GREGORIAN",
    "X-WR-TIMEZONE:Europe/Moscow",
    "BEGIN:VTIMEZONE",
    "TZID:Europe/Moscow",
    "X-LIC-LOCATION:Europe/Moscow",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0300",
    "TZOFFSETTO:+0300",
    "TZNAME:MSK",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def build_club_calendar(*, week_start: date, data: dict | None = None, club_id: int, club_name: str, snapshot=None, db=None) -> str:
    """Совместимый режим «одна неделя» (?week=)."""
    snap = snapshot if snapshot is not None else occ_src.load_snapshot(db)
    events = [e for e in occ_src.week_events(snap, week_start) if e["club_id"] == club_id]
    return generate_ics({"club_name": club_name, "events": events})


def build_calendar(snap, date_from: date, date_to: date, *, club_ids=None, session_ids=None, title: str = "", now: datetime | None = None) -> str:
    occurrences = occ_src.snapshot_occurrences(snap, date_from, date_to, session_ids=session_ids)
    wanted_clubs = set(club_ids) if club_ids is not None else None
    current = now or datetime.now(timezone.utc)
    stamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = list(_HEADER)
    if title:
        lines.insert(4, "X-WR-CALNAME:" + title.replace("\n", " ").replace(",", "\\,").replace(";", "\\;"))
    for occ in occurrences:
        if not occ.occupies:
            continue
        if wanted_clubs is not None and occ.club_id not in wanted_clubs:
            continue
        event = occ_src.occurrence_event(snap, occ)
        if event is None:
            continue
        parsed = _parse_schedule({"club_name": event["club_name"], "events": [_ics_event(event)]})
        lines.extend(_event_lines(parsed.club_name, parsed.events[0], stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(physical for line in lines for physical in _fold_line(line)) + "\r\n"


def _ics_event(event: dict) -> dict:
    return {
        "event_id": event["event_id"],
        "date": event["date"],
        "start_time": event["start_time"],
        "end_time": event["end_time"],
        "room_name": ", ".join(event.get("room_names") or [event["room_name"]]) or "—",
        "leader_name": ", ".join(event.get("leader_names") or [event["leader_name"]]) or "—",
        "status": event["status"],
        "comment": event.get("comment") or "",
    }


def build_club_calendar_range(*, start: date, end: date, club_id: int, club_name: str, data: dict | None = None, snapshot=None, db=None) -> str:
    """Диапазон дат одного кружка (совместимость с T4) — те же occurrence, что и в build_calendar."""
    snap = snapshot if snapshot is not None else occ_src.load_snapshot(db)
    return build_calendar(snap, start, end, club_ids=[club_id], title=club_name)
