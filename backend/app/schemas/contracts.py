"""Общий формат подготовленного события; остальные DTO согласовать по контракту."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, field_serializer


class ScheduleEvent(BaseModel):
    # event_id идентифицирует occurrence, а не всю серию регулярных занятий.
    event_id: str
    session_id: int
    club_id: int
    club_name: str
    category_id: int
    category_name: str
    category_color: str
    leader_id: int
    leader_name: str
    room_id: int
    room_name: str
    date: date
    start_time: time
    end_time: time
    status: Literal["scheduled", "cancelled", "moved"]
    original_date: date
    comment: str = ""
    # только для status="moved": исходное время (до переноса) — приложение рисует «Перенесено» в старом слоте
    original_start_time: time | None = None
    original_end_time: time | None = None

    @field_serializer("start_time", "end_time", "original_start_time", "original_end_time")
    def serialize_time(self, value: time | None) -> str | None:
        return value.strftime("%H:%M") if value is not None else None
