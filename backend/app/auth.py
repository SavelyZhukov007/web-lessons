"""Пароли и серверные сессии администраторов."""
from __future__ import annotations

from hashlib import scrypt, sha256
import hmac
import secrets

PASSWORD_KDF = {
    "name": "scrypt",
    "n": 2**14,
    "r": 8,
    "p": 1,
    "dklen": 32,
    "salt_bytes": 16,
}


def normalize_login(login: str) -> str:
    normalized = login.strip().lower()
    if len(normalized) < 3 or len(normalized) > 64 or any(char.isspace() for char in normalized):
        raise ValueError("Логин должен быть длиной 3–64 символа без пробелов")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Пароль должен содержать минимум 8 символов")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(PASSWORD_KDF["salt_bytes"])
    digest = scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_KDF["n"],
        r=PASSWORD_KDF["r"],
        p=PASSWORD_KDF["p"],
        dklen=PASSWORD_KDF["dklen"],
    )
    return "$".join(
        (
            PASSWORD_KDF["name"],
            str(PASSWORD_KDF["n"]),
            str(PASSWORD_KDF["r"]),
            str(PASSWORD_KDF["p"]),
            salt.hex(),
            digest.hex(),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = encoded_hash.split("$", 5)
    except ValueError:
        return False
    if scheme != PASSWORD_KDF["name"]:
        return False
    candidate = scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=int(n),
        r=int(r),
        p=int(p),
        dklen=len(bytes.fromhex(digest_hex)),
    )
    return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
