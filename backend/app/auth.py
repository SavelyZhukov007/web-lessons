"""Пароли и серверные сессии администраторов."""

from __future__ import annotations

import hmac
import os
import secrets
from hashlib import scrypt, sha256

# SEC-11: N=2^16 (64 МиБ, ~150–250 мс). Старые хэши (2^14) остаются валидными и пере-хэшируются при входе.
# SCRYPT_LOG_N нужен только тестам/слабому железу.
PASSWORD_KDF = {
    "name": "scrypt",
    "n": 2 ** int(os.getenv("SCRYPT_LOG_N", "16")),
    "r": 8,
    "p": 1,
    "dklen": 32,
    "salt_bytes": 16,
}


def normalize_login(login: str) -> str:
    normalized = login.strip().lower()
    if (
        len(normalized) < 3
        or len(normalized) > 64
        or any(char.isspace() for char in normalized)
    ):
        raise ValueError("Логин должен быть длиной 3–64 символа без пробелов")
    return normalized


MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "10"))
_COMMON_PASSWORDS = {
    "password", "password1", "password12", "qwertyuiop", "1234567890", "12345678910", "qwerty12345",
    "adminadmin", "administrator", "letmein123", "iloveyou123", "пароль123", "йцукен123",
}


def validate_password(password: str, login: str | None = None) -> None:
    """SEC-06: длина ≥ 10, не из стоп-листа, не равен логину, не из одного повторяющегося символа."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен содержать минимум {MIN_PASSWORD_LENGTH} символов")
    if len(password) > 255:
        raise ValueError("Пароль слишком длинный (максимум 255 символов)")
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(password)) < 4:
        raise ValueError("Пароль слишком простой — выбери другой")
    if login and lowered == login.strip().lower():
        raise ValueError("Пароль не должен совпадать с логином")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=256 * 1024 * 1024)


def hash_password(password: str, *, validate: bool = True) -> str:
    if validate:
        validate_password(password)
    salt = secrets.token_bytes(PASSWORD_KDF["salt_bytes"])
    digest = _scrypt(
        password, salt, PASSWORD_KDF["n"], PASSWORD_KDF["r"], PASSWORD_KDF["p"], PASSWORD_KDF["dklen"]
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
    candidate = _scrypt(
        password, bytes.fromhex(salt_hex), int(n), int(r), int(p), len(bytes.fromhex(digest_hex))
    )
    return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))


def needs_rehash(encoded_hash: str) -> bool:
    """True, если хэш посчитан слабее текущих параметров (rehash-on-login)."""
    try:
        _, n, r, p, _, _ = encoded_hash.split("$", 5)
        return (int(n), int(r), int(p)) != (PASSWORD_KDF["n"], PASSWORD_KDF["r"], PASSWORD_KDF["p"])
    except ValueError:
        return True


_dummy_hash: str | None = None


def verify_dummy(password: str) -> None:
    """SEC-10: для несуществующего логина тратим то же время, что и на настоящий хэш."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16), validate=False)
    verify_password(password, _dummy_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
