from .common import InputSchema, Name, PositiveCapacity, Text, UpdateSchema

class RoomCreate(InputSchema):
    name: Name
    building: Text = ""
    capacity: PositiveCapacity

class RoomUpdate(UpdateSchema):
    name: Name | None = None
    building: Text | None = None
    capacity: PositiveCapacity | None = None