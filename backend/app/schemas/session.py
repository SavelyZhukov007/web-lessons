from pydantic import ConfigDict, model_validator

from .common import Clock, IntervalSchema, LocalDate, PositiveId, UpdateSchema, Weekday
from .room import RoomRead


class SessionCreate(IntervalSchema):
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock
    one_off_date: LocalDate | None = None

    @model_validator(mode="after")
    def validate_one_off_day(self):
        if self.one_off_date and self.one_off_date.isoweekday() != self.weekday:
            raise ValueError("День недели должен совпадать с датой разового занятия")
        return self


class SessionUpdate(UpdateSchema, IntervalSchema):
    club_id: PositiveId | None = None
    room_id: PositiveId | None = None
    weekday: Weekday | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    one_off_date: LocalDate | None = None
    # Если передано только одно время, сравнение с сохранённым значением делает сервис.


class SessionRead(IntervalSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock
    one_off_date: LocalDate | None = None


class SessionWithRoomRead(SessionRead):
    room: RoomRead
