"""JWT (HS256) для админ-сессий. Токен — «обёртка» над серверной сессией:
подпись + срок проверяются здесь, а отзыв (logout, смена пароля) — строкой admin_sessions по хэшу jti."""
from __future__ import annotations

from datetime import datetime, timezone

import jwt

from .. import settings

ALGORITHM = "HS256"


def issue_token(*, admin_id: int, session_id: int, jti: str, issued_at: datetime, expires_at: datetime) -> str:
    def ts(dt: datetime) -> int:
        return int(dt.replace(tzinfo=timezone.utc).timestamp())

    claims = {
        "iss": settings.jwt_issuer(),
        "sub": str(admin_id),
        "sid": session_id,
        "jti": jti,
        "iat": ts(issued_at),
        "exp": ts(expires_at),
    }
    return jwt.encode(claims, settings.jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Возвращает claims или None (плохая подпись/срок/issuer/формат). Алгоритм жёстко HS256 (защита от alg=none)."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer(),
            options={"require": ["exp", "iat", "sub", "sid", "jti", "iss"]},
        )
    except jwt.PyJWTError:
        return None
