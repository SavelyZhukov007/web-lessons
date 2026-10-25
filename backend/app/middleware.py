"""Сквозные middleware: request-id + access-log, security headers/CSP, CSRF по Origin (SEC-04/05, OPS-03)."""
from __future__ import annotations

import logging
import time
import uuid
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import settings
from .services import audit

access_logger = logging.getLogger("clubs.access")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def _origin_allowed(request: Request, origin: str) -> bool:
    host = request.headers.get("host", "")
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.netloc == host:
        return True
    return origin.rstrip("/") in settings.trusted_origins()


def csrf_violation(request: Request) -> bool:
    """Cookie-аутентификация + небезопасный метод + чужой Origin/Sec-Fetch-Site → блокируем.
    Запросы с Authorization: Bearer не используют cookie → CSRF неприменим. Запросы без Origin (curl, тесты) не браузерные."""
    if request.method not in UNSAFE:
        return False
    if request.headers.get("authorization", "")[:7].lower() == "bearer ":
        return False
    if "admin_session" not in request.cookies:
        return False
    origin = request.headers.get("origin")
    if origin is not None:
        return not _origin_allowed(request, origin)
    return request.headers.get("sec-fetch-site", "").lower() == "cross-site"


def _security_headers(response: Response, request: Request) -> None:
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not request.url.path.startswith("/api/"):
        h.setdefault("Content-Security-Policy", CSP)
    if settings.is_production() or request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith(("/api/admin", "/api/push/status")):
        h["Cache-Control"] = "no-store"


async def request_pipeline(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    started = time.perf_counter()

    if csrf_violation(request):
        response: Response = JSONResponse({"detail": "Запрос отклонён: недопустимый Origin"}, status_code=403)
    else:
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            access_logger.exception("unhandled error request_id=%s path=%s", request_id, request.url.path)
            response = JSONResponse({"detail": "Внутренняя ошибка сервера", "request_id": request_id}, status_code=500)

    _security_headers(response, request)
    response.headers["X-Request-ID"] = request_id
    path = request.url.path
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/admin/") and response.status_code < 400
            and path not in ("/api/admin/login", "/api/admin/logout", "/api/admin/password")):
        audit.log("admin_write", admin_id=getattr(request.state, "admin_id", None), method=request.method, path=path,
                  status=response.status_code, request_id=request_id)  # кто и что менял (без тел запросов)
    access_logger.info(
        "%s %s -> %s %.1fms request_id=%s ip=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
        request.client.host if request.client else "-",
    )
    return response
