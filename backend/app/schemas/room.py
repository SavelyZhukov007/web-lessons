from pydantic import ConfigDict, StrictBool, model_validator

from .common import InputSchema, Name, PositiveCapacity, ShortText


class RoomCreate(InputSchema):
    name: Name
    building: ShortText | None = None
    capacity: PositiveCapacity | None = None
    is_remote: StrictBool = False
    remote_url: ShortText = ""
    remote_instructions: ShortText = ""


class RoomUpdate(InputSchema):
    name: Name | None = None
    building: ShortText | None = None
    capacity: PositiveCapacity | None = None
    is_remote: StrictBool | None = None
    remote_url: ShortText | None = None
    remote_instructions: ShortText | None = None

    @model_validator(mode="before")
    @classmethod
    def required_fields_not_null(cls, value):
        if isinstance(value, dict) and any(k in value and value[k] is None for k in ("name", "is_remote", "remote_url", "remote_instructions")):
            raise ValueError("Название и параметры формата не могут быть null")
        return value


class RoomRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    building: ShortText | None
    capacity: PositiveCapacity | None
    is_remote: StrictBool = False
    remote_url: ShortText = ""
    remote_instructions: ShortText = ""
