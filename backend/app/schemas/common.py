"""Независимые входные типы"""

import re
from datetime import date
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PositiveId = Annotated[int, Field(strict=True, gt=0)]
PositiveCapacity = PositiveId
Weekday = Annotated[int, Field(strict=True, ge=1, le=6)]
# SEC-09: верхние границы на все строки (иначе мегабайты в БД и в ответ)
Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)
]
Text = Annotated[str, StringConstraints(strict=True, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strict=True, max_length=300)]
Clock = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(?:0[89]|1[0-9]|20):[0-5][0-9]$|^21:00$"),
]
Color = Annotated[str, StringConstraints(strict=True, pattern=r"^#[0-9a-fA-F]{6}$")]


def parse_date(value):
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        raise ValueError("Дата должна иметь формат YYYY-MM-DD")
    return date.fromisoformat(value)


LocalDate = Annotated[date, BeforeValidator(parse_date)]


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateSchema(InputSchema):
    # только для patch
    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if isinstance(value, dict):
            null_fields = [key for key, item in value.items() if item is None]
            if null_fields:
                raise ValueError("null недопустим: " + ", ".join(null_fields))
        return value


class IntervalSchema(InputSchema):
    @model_validator(mode="after")
    def validate_interval(self):
        start = getattr(self, "start_time", None)
        end = getattr(self, "end_time", None)
        if start is not None and end is not None and start >= end:
            raise ValueError("Начало занятия должно быть раньше конца")
        return self
