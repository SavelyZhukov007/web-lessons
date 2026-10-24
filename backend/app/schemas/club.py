from pydantic import ConfigDict, StrictBool

from .category import CategoryRead
from .common import InputSchema, Name, PositiveId, Text, UpdateSchema
from .leader import LeaderRead
from .session import SessionWithRoomRead
from .session_exception import SessionExceptionRead


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


class ClubRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    description: Text
    category_id: PositiveId
    leader_id: PositiveId
    is_active: StrictBool


class ClubDetailRead(ClubRead):
    category: CategoryRead
    leader: LeaderRead
    sessions: list[SessionWithRoomRead]
    upcoming_exceptions: list[SessionExceptionRead]
