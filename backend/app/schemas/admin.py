from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

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


class LoginResponse(AdminStatusResponse):
    """Для браузера достаточно cookie; access_token — для мобильного приложения (Authorization: Bearer)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # секунды жизни access_token
    refresh_expires_in: int


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: Annotated[str, StringConstraints(strict=True, min_length=10, max_length=200)] | None = None


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: Password
    new_password: Password
