from pydantic import ConfigDict, Field, StrictBool

from .category import CategoryRead
from .common import InputSchema, Name, PositiveId, Text, UpdateSchema
from .contracts import ScheduleEvent
from .leader import LeaderRead
from .session import SessionWithRoomRead
from .session_exception import SessionExceptionRead


class ClubCreate(InputSchema):
    name: Name
    description: Text = ""
    category_id: PositiveId
    leader_id: PositiveId
    is_active: StrictBool = True
    leader_ids: list[PositiveId] = Field(default_factory=list, max_length=30)


class ClubUpdate(UpdateSchema):
    name: Name | None = None
    description: Text | None = None
    category_id: PositiveId | None = None
    leader_id: PositiveId | None = None
    is_active: StrictBool | None = None
    leader_ids: list[PositiveId] | None = Field(default=None, max_length=30)


class ClubRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    description: Text
    category_id: PositiveId
    leader_id: PositiveId
    is_active: StrictBool
    leader_ids: list[PositiveId] = Field(default_factory=list)


class ClubDetailRead(ClubRead):
    category: CategoryRead
    leader: LeaderRead
    leaders: list[LeaderRead] = Field(default_factory=list)
    sessions: list[SessionWithRoomRead]
    upcoming_exceptions: list[SessionExceptionRead]
    upcoming_events: list[ScheduleEvent] = Field(default_factory=list)
