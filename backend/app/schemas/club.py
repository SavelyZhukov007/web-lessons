from pydantic import StrictBool
from .common import InputSchema, Name, PositiveId, Text, UpdateSchema

class ClubCreate(InputSchema):
    name: Name
    description: Text = ""
    category_id: PositiveId
    leader_id: PositiveId
    is_active: StrictBool = True

class ClubUpdate(UpdateSchema):
    name: Name | None = None
    description: Text | None = None
    category_id: PositiveId | None = None
    leader_id: PositiveId | None = None
    is_active: StrictBool | None = None
