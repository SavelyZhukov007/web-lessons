from datetime import date, timedelta

from pydantic import ConfigDict, model_validator

from .common import InputSchema, LocalDate, Name, PositiveId, ShortText


class PeriodInput(InputSchema):
    name: Name
    start_date: LocalDate
    end_date: LocalDate
    even_week_start: LocalDate

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date > self.end_date or self.end_date - self.start_date > timedelta(days=1096):
            raise ValueError("Период должен длиться не более трёх лет, начало не позже конца")
        if self.start_date < date(2000, 1, 3) or self.end_date > date(2101, 1, 2):
            raise ValueError("Период выходит за пределы поддерживаемого календаря")
        if self.even_week_start.weekday() != 0:
            raise ValueError("Опорная чётная неделя должна начинаться в понедельник")
        if not self.start_date - timedelta(days=6) <= self.even_week_start <= self.end_date:
            raise ValueError("Опорная неделя должна пересекаться с периодом")
        return self


class PeriodRead(PeriodInput):
    model_config = ConfigDict(from_attributes=True)
    id: PositiveId


class NoClassInput(InputSchema):
    date: LocalDate
    reason: ShortText = ""


class NoClassRead(NoClassInput):
    model_config = ConfigDict(from_attributes=True)
    id: PositiveId
    period_id: PositiveId


class NoClassRange(InputSchema):
    start_date: LocalDate
    end_date: LocalDate
    reason: ShortText = ""

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date or self.end_date - self.start_date > timedelta(days=365):
            raise ValueError("Диапазон должен быть не более 366 дней")
        return self
