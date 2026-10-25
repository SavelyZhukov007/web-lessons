"""Единая конфигурация из переменных окружения (SEC-02, OPS-02).

ENV=development (по умолчанию) | production | test.
В production небезопасные значения не принимаются: приложение не стартует (validate_for_startup()).
Значения читаются лениво — так их удобно подменять в тестах.
"""
from __future__ import annotations

import os
import secrets
import stat
import threading
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TRUE = {"1", "true", "yes", "on"}


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else raw.strip().lower() in _TRUE


def _list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def env() -> str:
    return os.getenv("ENV", "development").strip().lower()


def is_production() -> bool:
    return env() == "production"


def cookie_secure() -> bool:
    """В production Secure включён всегда (по умолчанию и принудительно). В dev — выключен, если не задано COOKIE_SECURE=true."""
    return True if is_production() else _bool("COOKIE_SECURE", False)


def docs_enabled() -> bool:
    return _bool("ENABLE_DOCS", not is_production())


def allowed_hosts() -> list[str]:
    """TrustedHostMiddleware. Пусто => не проверяется (только dev)."""
    return _list("ALLOWED_HOSTS")


def trusted_origins() -> list[str]:
    """Дополнительные Origin, которым разрешены cookie-запросы на запись (CSRF-проверка) — SEC-04."""
    return [o.rstrip("/") for o in _list("TRUSTED_ORIGINS")]


# origin WebView приложения (Capacitor: androidScheme http/https, iOS capacitor://). Только Bearer, без cookie —
# поэтому разрешать их безопасно; отключить: CORS_APP_ORIGINS=0.
APP_ORIGINS = ["http://localhost", "https://localhost", "capacitor://localhost"]


def cors_origins() -> list[str]:
    """CORS: CORS_ORIGINS + origin приложения (если не CORS_APP_ORIGINS=0)."""
    extra = [o.rstrip("/") for o in _list("CORS_ORIGINS")]
    app = APP_ORIGINS if _bool("CORS_APP_ORIGINS", True) else []
    return list(dict.fromkeys(extra + app))


def server_name() -> str:
    """Имя сервера для приложения (поиск в сети, бейдж «Тестовый сервер: …»)."""
    return (os.getenv("SERVER_NAME") or "KipClub").strip()[:60]


def mdns_enabled() -> bool:
    """Объявлять сервер в локальной сети (_itc-kruzhki._tcp, нужен пакет zeroconf). По умолчанию выключено."""
    return _bool("MDNS_ENABLED", False)


def logs_dir() -> Path:
    return Path(os.getenv("APP_LOGS_DIR") or Path(__file__).resolve().parents[2] / "data" / "client-logs").resolve()


def logs_retention_days() -> int:
    try:
        return min(21, max(1, int(os.getenv("LOGS_RETENTION_DAYS", "14"))))  # журнал клиентов храним не дольше 21 дня
    except ValueError:
        return 14


def session_lifetime() -> timedelta:
    """Срок жизни refresh-токена/серверной сессии (скользящий: продлевается при каждой ротации)."""
    return timedelta(hours=float(os.getenv("SESSION_HOURS", "168")))


def access_lifetime() -> timedelta:
    """Срок жизни access-JWT (короткий; дальше клиент делает POST /api/admin/refresh)."""
    return timedelta(minutes=float(os.getenv("ACCESS_MINUTES", "15")))


def refresh_grace_seconds() -> int:
    """Окно, в котором повтор уже ротированного refresh-токена считается гонкой вкладок/потерянным ответом (409), а не кражей."""
    return int(os.getenv("REFRESH_GRACE_SECONDS", "10"))


def jwt_issuer() -> str:
    return "clubs-schedule"


_secret_lock = threading.Lock()


def jwt_secret_file() -> Path:
    custom = os.getenv("JWT_SECRET_FILE")
    return Path(custom) if custom else ROOT / "jwt_secret.key"


def jwt_secret() -> str:
    """JWT_SECRET (env) → иначе файл JWT_SECRET_FILE (создаётся один раз с правами 600, в .gitignore)."""
    from_env = os.getenv("JWT_SECRET", "").strip()
    if from_env:
        return from_env
    with _secret_lock:
        path = jwt_secret_file()
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return value


def rustore_url() -> str | None:
    """Ссылка на приложение в RuStore. Пока не задана — блок RuStore на /android/ скрыт."""
    url = os.getenv("RUSTORE_URL", "").strip()
    return url if url.startswith("https://") else None


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()


def log_json() -> bool:
    return _bool("LOG_JSON", is_production())


def audit_log_path() -> str | None:
    return os.getenv("AUDIT_LOG_FILE") or None


def validate_for_startup(db_path: Path) -> list[str]:
    """Список проблем конфигурации. В production любая проблема — отказ стартовать."""
    problems: list[str] = []
    if not is_production():
        return problems
    if os.getenv("COOKIE_SECURE", "true").strip().lower() not in _TRUE:
        problems.append("COOKIE_SECURE=false в production запрещён (cookie сессии без Secure).")
    effective_secret = os.getenv("JWT_SECRET", "").strip()
    if not effective_secret:
        try:
            effective_secret = jwt_secret_file().read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            problems.append("JWT_SECRET_FILE отсутствует или не читается; задайте JWT_SECRET или файл с секретом.")
    if len(effective_secret) < 32:
        problems.append("JWT_SECRET (или содержимое JWT_SECRET_FILE) слишком короткий: нужно ≥ 32 непробельных символов.")
    hosts = allowed_hosts()
    if not hosts or "*" in hosts:
        problems.append("Задай ALLOWED_HOSTS=домен1,домен2 (без '*') — защита от подмены Host.")
    try:
        db_path.resolve().relative_to(ROOT)
        if not _bool("ALLOW_DB_IN_APP_DIR", False):
            problems.append(
                f"БД лежит внутри каталога приложения ({db_path}). Укажи CLUBS_SCHEDULE_DB_PATH вне репозитория, например /data/clubs.sqlite3."
            )
    except ValueError:
        pass
    if docs_enabled():
        problems.append("ENABLE_DOCS=true в production: /docs и /openapi.json должны быть выключены.")
    return problems
