from pydantic import BaseModel, ConfigDict, StringConstraints
from typing import Annotated

LoginName = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=3, max_length=64),
]
Password = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=255)]


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: LoginName
    password: Password


class AdminSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: LoginName


class AdminStatusResponse(BaseModel):
    admin: AdminSummary
    status: str = "authenticated"
