from pydantic import ConfigDict

from .common import InputSchema, Name, PositiveCapacity, ShortText, UpdateSchema


class RoomCreate(InputSchema):
    name: Name
    building: ShortText = ""
    capacity: PositiveCapacity


class RoomUpdate(UpdateSchema):
    name: Name | None = None
    building: ShortText | None = None
    capacity: PositiveCapacity | None = None


class RoomRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    building: ShortText
    capacity: PositiveCapacity
