from pydantic import ConfigDict
from .common import InputSchema, Name, Text, UpdateSchema

class LeaderCreate(InputSchema):
    name: Name
    position: Text = ""
    contact: Text = ""

class LeaderUpdate(UpdateSchema):
    name: Name | None = None
    position: Text | None = None
    contact: Text | None = None


class LeaderRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    position: Text
    contact: Text