from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .common import Clock, IntervalSchema, LocalDate, PositiveId, Weekday
from .leader import LeaderPublic
from .room import RoomRead


class SessionCreate(IntervalSchema):
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock
    one_off_date: LocalDate | None = None
    period_id: PositiveId | None = None
    repeat: Literal["weekly", "even", "odd", "once"] = "weekly"
    leader_ids: list[PositiveId] = Field(default_factory=list, max_length=30)
    room_ids: list[PositiveId] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_one_off_day(self):
        if self.one_off_date and self.one_off_date.isoweekday() != self.weekday:
            raise ValueError("День недели должен совпадать с датой разового занятия")
        if self.one_off_date and self.repeat == "weekly":
            self.repeat = "once"
        if (self.repeat == "once") != bool(self.one_off_date):
            raise ValueError("Разовое занятие должно иметь дату")
        if self.repeat in ("even", "odd") and not self.period_id:
            raise ValueError("Для чётных и нечётных недель необходим учебный период")
        return self


class SessionUpdate(IntervalSchema):
    club_id: PositiveId | None = None
    room_id: PositiveId | None = None
    weekday: Weekday | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    one_off_date: LocalDate | None = None
    period_id: PositiveId | None = None
    repeat: Literal["weekly", "even", "odd", "once"] | None = None
    leader_ids: list[PositiveId] | None = Field(default=None, max_length=30)
    room_ids: list[PositiveId] | None = Field(default=None, max_length=30)
    # Если передано только одно время, сравнение с сохранённым значением делает сервис.

    @model_validator(mode="before")
    @classmethod
    def reject_invalid_nulls(cls, value):
        if isinstance(value, dict):
            invalid = [k for k, v in value.items() if v is None and k not in {"period_id", "one_off_date"}]
            if invalid:
                raise ValueError("null недопустим: " + ", ".join(invalid))
        return value


class SessionRead(IntervalSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock
    one_off_date: LocalDate | None = None
    period_id: PositiveId | None = None
    repeat: Literal["weekly", "even", "odd", "once"] = "weekly"
    leader_ids: list[PositiveId] = Field(default_factory=list)
    room_ids: list[PositiveId] = Field(default_factory=list)


class SessionWithRoomRead(SessionRead):
    room: RoomRead
    rooms: list[RoomRead] = Field(default_factory=list)
    leaders: list[LeaderPublic] = Field(default_factory=list)
    # schedule v2: тип повторения и ближайшие реальные даты (occurrence_source)
    repeat: str | None = None
    repeat_label: str | None = None
    next_dates: list[str] = []
