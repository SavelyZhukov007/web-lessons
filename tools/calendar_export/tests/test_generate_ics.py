from datetime import datetime, timezone

import pytest

from tools.calendar_export.generate_ics import ScheduleDataError, generate_ics

FIXED_NOW = datetime(2026, 10, 17, 12, 30, tzinfo=timezone.utc)


def sample_schedule():
    return {
        "club_name": "Кружок «Робототехника, шаг за шагом»",
        "events": [
            {
                "event_id": "session-1:2026-10-19",
                "date": "2026-10-19",
                "start_time": "15:00",
                "end_time": "16:30",
                "room_name": "Лаборатория 303, корпус «Технопарк»",
                "leader_name": "Анна Смирнова",
                "status": "scheduled",
            },
            {
                "event_id": "session-1:2026-10-26",
                "date": "2026-10-26",
                "start_time": "17:00",
                "end_time": "18:00",
                "room_name": "Кабинет 5",
                "leader_name": "Анна Смирнова",
                "status": "moved",
                "comment": "Перенос, комментарий; путь\\вариант\nследующая строка",
            },
            {
                "event_id": "session-1:2026-11-02",
                "date": "2026-11-02",
                "start_time": "15:00",
                "end_time": "16:30",
                "room_name": "Кабинет 5",
                "leader_name": "Анна Смирнова",
                "status": "cancelled",
            },
        ],
    }


def unfold(content):
    return content.replace("\r\n ", "")


def test_exports_active_and_moved_events_with_moscow_timezone():
    content = generate_ics(sample_schedule(), now=FIXED_NOW)
    logical_lines = unfold(content).split("\r\n")

    assert "TZID:Europe/Moscow" in logical_lines
    assert "TZOFFSETTO:+0300" in logical_lines
    assert sum(line == "BEGIN:VEVENT" for line in logical_lines) == 2
    assert "DTSTART;TZID=Europe/Moscow:20261019T150000" in logical_lines
    assert "DTEND;TZID=Europe/Moscow:20261026T180000" in logical_lines
    assert "SUMMARY:Кружок «Робототехника\\, шаг за шагом»" in logical_lines
    assert "STATUS:CONFIRMED" in logical_lines
    assert (
        "DESCRIPTION:Руководитель: Анна Смирнова\\nСтатус: занятие перенесено\\nКомментарий: Перенос\\, комментарий\\; путь\\\\вариант\\nследующая строка"
        in logical_lines
    )
    assert not any("20261102" in line for line in logical_lines)


def test_event_uid_is_stable_across_exports():
    first = generate_ics(sample_schedule(), now=FIXED_NOW)
    second = generate_ics(
        sample_schedule(), now=datetime(2027, 1, 1, tzinfo=timezone.utc)
    )

    first_uids = [
        line for line in unfold(first).split("\r\n") if line.startswith("UID:")
    ]
    second_uids = [
        line for line in unfold(second).split("\r\n") if line.startswith("UID:")
    ]
    assert first_uids == second_uids
    assert len(set(first_uids)) == 2


def test_long_unicode_lines_are_folded_at_75_utf8_octets():
    schedule = sample_schedule()
    schedule["club_name"] = "Р" * 100
    content = generate_ics(schedule, now=FIXED_NOW)

    assert all(
        len(line.encode("utf-8")) <= 75 for line in content.split("\r\n") if line
    )
    assert "SUMMARY:" + "Р" * 100 in unfold(content)


def test_empty_schedule_is_a_valid_calendar():
    content = generate_ics({"club_name": "Нет занятий", "events": []}, now=FIXED_NOW)
    logical_lines = unfold(content).split("\r\n")

    assert logical_lines[0] == "BEGIN:VCALENDAR"
    assert logical_lines[-2] == "END:VCALENDAR"
    assert "BEGIN:VEVENT" not in logical_lines


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda data: data.update(events="not a list"), "events: ожидается массив"),
        (lambda data: data["events"][0].update(date="2026-02-30"), "существующая дата"),
        (lambda data: data["events"][0].update(start_time="25:00"), "формате HH:MM"),
        (lambda data: data["events"][0].update(end_time="14:00"), "раньше конца"),
        (
            lambda data: data["events"][0].update(status="pending"),
            "допустимые значения",
        ),
        (lambda data: data["events"][0].update(room_name=""), "не должно быть пустым"),
    ],
)
def test_invalid_schedule_has_clear_error(mutate, error):
    schedule = sample_schedule()
    mutate(schedule)

    with pytest.raises(ScheduleDataError, match=error):
        generate_ics(schedule, now=FIXED_NOW)


def test_duplicate_event_ids_are_rejected():
    schedule = sample_schedule()
    schedule["events"][1]["event_id"] = schedule["events"][0]["event_id"]

    with pytest.raises(ScheduleDataError, match="повторяется идентификатор"):
        generate_ics(schedule, now=FIXED_NOW)


def test_naive_export_timestamp_is_rejected():
    with pytest.raises(ValueError, match="должен содержать часовой пояс"):
        generate_ics({"club_name": "Кружок", "events": []}, now=datetime(2026, 1, 1))
