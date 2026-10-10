from typing import Literal
from pydantic import model_validator
from .common import Clock, InputSchema, LocalDate, PositiveId, Text, UpdateSchema


class CancellationCreate(InputSchema):
    session_id: PositiveId
    original_date: LocalDate
    type: Literal["cancelled"] = "cancelled"
    comment: Text = ""


class CancellationUpdate(UpdateSchema):
    session_id: PositiveId | None = None
    original_date: LocalDate | None = None
    type: Literal["cancelled"] | None = None
    comment: Text | None = None


class MoveInterval(InputSchema):
    @model_validator(mode="after")
    def validate_interval(self):
        start = getattr(self, "new_start_time", None)
        end = getattr(self, "new_end_time", None)
        if start is not None and end is not None and start >= end:
            raise ValueError("Начало переноса должно быть раньше конца")
        return self

class MoveCreate(MoveInterval):
    session_id: PositiveId
    original_date: LocalDate
    type: Literal["moved"] = "moved"
    new_date: LocalDate
    new_start_time: Clock
    new_end_time: Clock
    new_room_id: PositiveId
    comment: Text = ""

class MoveUpdate(UpdateSchema, MoveInterval):
    session_id: PositiveId | None = None
    original_date: LocalDate | None = None
    type: Literal["moved"] | None = None
    new_date: LocalDate | None = None
    new_start_time: Clock | None = None
    new_end_time: Clock | None = None
    new_room_id: PositiveId | None = None
    comment: Text | None = None
    # Отдельный тип PATCH для существующего переноса; смена типа исключения не поддержана.
