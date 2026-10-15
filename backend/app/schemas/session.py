from pydantic import ConfigDict
from .common import Clock, IntervalSchema, PositiveId, UpdateSchema, Weekday
from .room import RoomRead

class SessionCreate(IntervalSchema):
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock

class SessionUpdate(UpdateSchema, IntervalSchema):
    club_id: PositiveId | None = None
    room_id: PositiveId | None = None
    weekday: Weekday | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    # Если передано только одно время, сравнение с сохранённым значением делает сервис.


class SessionRead(IntervalSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    club_id: PositiveId
    room_id: PositiveId
    weekday: Weekday
    start_time: Clock
    end_time: Clock


class SessionWithRoomRead(SessionRead):
    room: RoomRead