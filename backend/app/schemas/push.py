import base64
import binascii
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from .common import InputSchema, PositiveId


def _b64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    try:
        base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Ожидается base64url-строка") from exc
    return value


def _endpoint(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("endpoint должен быть абсолютным URL")
    return value


Endpoint = Annotated[
    str,
    StringConstraints(strict=True, min_length=10, max_length=2048),
    AfterValidator(_endpoint),
]
KeyString = Annotated[
    str,
    StringConstraints(strict=True, min_length=8, max_length=255, pattern=r"^[A-Za-z0-9_-]+={0,2}$"),
    AfterValidator(_b64url),
]


class PushKeys(InputSchema):
    p256dh: KeyString
    auth: KeyString

    @model_validator(mode="after")
    def check_lengths(self):
        # p256dh — несжатая точка P-256 (65 байт), auth — 16 байт
        if len(base64.urlsafe_b64decode(self.p256dh + "=" * (-len(self.p256dh) % 4))) != 65:
            raise ValueError("keys.p256dh: ожидается 65 байт (несжатая точка P-256)")
        if len(base64.urlsafe_b64decode(self.auth + "=" * (-len(self.auth) % 4))) != 16:
            raise ValueError("keys.auth: ожидается 16 байт")
        return self


class PushSubscribeRequest(InputSchema):
    endpoint: Endpoint
    keys: PushKeys
    club_id: PositiveId | None = None  # None — все кружки
    expirationTime: float | None = Field(default=None)  # приходит из PushSubscription.toJSON(); игнорируется


class PushUnsubscribeRequest(InputSchema):
    endpoint: Endpoint
    club_id: PositiveId | None = None  # None — удалить ВСЕ подписки этого endpoint


class PushStatusRequest(InputSchema):
    endpoint: Endpoint
