from pydantic import ConfigDict

from .common import InputSchema, Name, ShortText, UpdateSchema


class LeaderCreate(InputSchema):
    name: Name
    position: ShortText = ""
    contact: ShortText = ""


class LeaderUpdate(UpdateSchema):
    name: Name | None = None
    position: ShortText | None = None
    contact: ShortText | None = None


class LeaderRead(InputSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    position: ShortText
    contact: ShortText


class LeaderPublic(InputSchema):
    """Публичный список руководителей: без контактов (SEC-07). Контакт отдаёт только карточка активного кружка."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Name
    position: ShortText
