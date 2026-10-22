"""Generate an iCalendar file from a single-club schedule JSON document."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
ALLOWED_STATUSES = {"scheduled", "moved", "cancelled"}


class ScheduleDataError(ValueError):
    """Raised when the input JSON does not match the documented schedule format."""


@dataclass(frozen=True)
class Event:
    event_id: str
    date: date
    start_time: str
    end_time: str
    room_name: str
    leader_name: str
    status: str
    comment: str


@dataclass(frozen=True)
class Schedule:
    club_name: str
    events: tuple[Event, ...]


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ScheduleDataError(f"{field}: ожидается строка")
    if not allow_empty and not value.strip():
        raise ScheduleDataError(f"{field}: значение не должно быть пустым")
    if any(ord(char) < 32 and char not in "\r\n" for char in value) or "\x7f" in value:
        raise ScheduleDataError(f"{field}: управляющие символы не допускаются")
    return value


def _parse_schedule(data: Any) -> Schedule:
    if not isinstance(data, dict):
        raise ScheduleDataError("Корневое значение JSON должно быть объектом")

    club_name = _text(data.get("club_name"), "club_name")
    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        raise ScheduleDataError("events: ожидается массив событий")

    events: list[Event] = []
    seen_ids: set[str] = set()
    for index, raw_event in enumerate(raw_events):
        prefix = f"events[{index}]"
        if not isinstance(raw_event, dict):
            raise ScheduleDataError(f"{prefix}: ожидается объект события")

        event_id = _text(raw_event.get("event_id"), f"{prefix}.event_id")
        if event_id in seen_ids:
            raise ScheduleDataError(
                f"{prefix}.event_id: повторяется идентификатор {event_id!r}"
            )
        seen_ids.add(event_id)

        raw_date = _text(raw_event.get("date"), f"{prefix}.date")
        try:
            event_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ScheduleDataError(
                f"{prefix}.date: ожидается существующая дата в формате YYYY-MM-DD"
            ) from exc
        if event_date.isoformat() != raw_date:
            raise ScheduleDataError(f"{prefix}.date: ожидается формат YYYY-MM-DD")

        start_time = _text(raw_event.get("start_time"), f"{prefix}.start_time")
        end_time = _text(raw_event.get("end_time"), f"{prefix}.end_time")
        if not TIME_PATTERN.fullmatch(start_time):
            raise ScheduleDataError(
                f"{prefix}.start_time: ожидается время в формате HH:MM"
            )
        if not TIME_PATTERN.fullmatch(end_time):
            raise ScheduleDataError(
                f"{prefix}.end_time: ожидается время в формате HH:MM"
            )
        if start_time >= end_time:
            raise ScheduleDataError(
                f"{prefix}: начало занятия должно быть раньше конца"
            )

        room_name = _text(raw_event.get("room_name"), f"{prefix}.room_name")
        leader_name = _text(raw_event.get("leader_name"), f"{prefix}.leader_name")
        status = _text(raw_event.get("status"), f"{prefix}.status")
        if status not in ALLOWED_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_STATUSES))
            raise ScheduleDataError(f"{prefix}.status: допустимые значения: {allowed}")
        comment = _text(
            raw_event.get("comment", ""), f"{prefix}.comment", allow_empty=True
        )

        events.append(
            Event(
                event_id=event_id,
                date=event_date,
                start_time=start_time,
                end_time=end_time,
                room_name=room_name,
                leader_name=leader_name,
                status=status,
                comment=comment,
            )
        )

    return Schedule(club_name=club_name, events=tuple(events))


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold_line(line: str) -> list[str]:
    folded: list[str] = []
    current = ""
    byte_count = 0
    for char in line:
        char_bytes = len(char.encode("utf-8"))
        if byte_count + char_bytes > 75:
            folded.append(current)
            current = " "
            byte_count = 1
        current += char
        byte_count += char_bytes
    folded.append(current)
    return folded


def _format_date_time(event_date: date, time_text: str) -> str:
    hour, minute = (int(part) for part in time_text.split(":"))
    return f"{event_date:%Y%m%d}T{hour:02d}{minute:02d}00"


def _event_lines(club_name: str, event: Event, timestamp: str) -> list[str]:
    event_uid = hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()
    description = [f"Руководитель: {event.leader_name}"]
    if event.status == "moved":
        description.append("Статус: занятие перенесено")
    if event.comment:
        description.append(f"Комментарий: {event.comment}")
    return [
        "BEGIN:VEVENT",
        f"UID:{event_uid}@calendar-export.local",
        f"DTSTAMP:{timestamp}",
        f"DTSTART;TZID=Europe/Moscow:{_format_date_time(event.date, event.start_time)}",
        f"DTEND;TZID=Europe/Moscow:{_format_date_time(event.date, event.end_time)}",
        f"SUMMARY:{_escape_text(club_name)}",
        f"LOCATION:{_escape_text(event.room_name)}",
        f"DESCRIPTION:{_escape_text(chr(10).join(description))}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]


def generate_ics(data: Any, *, now: datetime | None = None) -> str:
    """Validate schedule data and return UTF-8 iCalendar text with CRLF line endings."""
    schedule = _parse_schedule(data)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now должен содержать часовой пояс")
    timestamp = current_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
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
    for event in schedule.events:
        if event.status != "cancelled":
            lines.extend(_event_lines(schedule.club_name, event, timestamp))
    lines.append("END:VCALENDAR")
    return (
        "\r\n".join(physical for line in lines for physical in _fold_line(line))
        + "\r\n"
    )


def load_schedule(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as input_file:
            return json.load(input_file)
    except json.JSONDecodeError as exc:
        raise ScheduleDataError(
            f"Некорректный JSON в {path} (строка {exc.lineno}, столбец {exc.colno}): {exc.msg}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ScheduleDataError(f"Файл {path} должен быть в кодировке UTF-8") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Создать календарный файл .ics из JSON с расписанием одного кружка."
    )
    parser.add_argument("input_json", type=Path, help="путь к входному JSON")
    parser.add_argument("output_ics", type=Path, help="путь к выходному .ics")
    args = parser.parse_args(argv)

    try:
        content = generate_ics(load_schedule(args.input_json))
        args.output_ics.write_bytes(content.encode("utf-8"))
    except (OSError, ScheduleDataError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
