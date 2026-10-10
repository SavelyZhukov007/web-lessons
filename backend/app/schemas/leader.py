from .common import InputSchema, Name, Text, UpdateSchema

class LeaderCreate(InputSchema):
    name: Name
    position: Text = ""
    contact: Text = ""

class LeaderUpdate(UpdateSchema):
    name: Name | None = None
    position: Text | None = None
    contact: Text | None = None