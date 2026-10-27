from typing import Literal

from pydantic import Field

from .common import Clock, InputSchema, Name, PositiveId, Weekday


class ImportUpload(InputSchema):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=4, max_length=800_000)


class ImportDecision(InputSchema):
    row: int = Field(ge=2)
    action: Literal["skip", "create"]
    club_id: PositiveId | None = None
    category_id: PositiveId | None = None
    leader_id: PositiveId | None = None
    leader_ids: list[PositiveId] = Field(default_factory=list, max_length=30)
    room_ids: list[PositiveId] = Field(default_factory=list, max_length=30)
    period_id: PositiveId | None = None
    repeat: Literal["weekly", "even", "odd"] = "weekly"
    weekday: Weekday | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    club_name: Name | None = None


class ImportDecisions(InputSchema):
    decisions: list[ImportDecision] = Field(max_length=500)
