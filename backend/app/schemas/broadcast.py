from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from .common import InputSchema, PositiveId

TITLE_MAX, BODY_MAX, URL_MAX = 80, 500, 300

Title = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]
Body = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=BODY_MAX)]
IdemKey = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{8,64}$")]


class AudienceIn(InputSchema):
    audience: Literal["all", "clubs"] = "all"
    club_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    session_ids: list[PositiveId] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def check_audience(self):
        if self.audience == "clubs" and not self.club_ids:
            raise ValueError("Выберите хотя бы один кружок или «Всем»")
        if self.audience == "all":
            self.club_ids, self.session_ids = [], []
        self.club_ids = sorted(set(self.club_ids))
        self.session_ids = sorted(set(self.session_ids))
        return self


class BroadcastCreate(AudienceIn):
    title: Title
    body: Body
    url: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=URL_MAX)] | None = None
    idempotency_key: IdemKey

    @field_validator("url")
    @classmethod
    def local_url(cls, v):
        if not v:
            return None
        if not v.startswith("/") or v.startswith("//") or "\\" in v or any(ch.isspace() for ch in v):
            raise ValueError("Ссылка — путь на этом сайте, например /club.html?id=3")
        return v
