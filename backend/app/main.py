import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import settings
from .database import DB_PATH, SessionLocal
from .logging_setup import configure_logging
from .middleware import request_pipeline
from .migrations import current_revision, head_revision, prepare_database
from .routers import admin, announcements, app_api, distribution, public, push

configure_logging()
log = logging.getLogger("clubs.app")

FRONTEND = Path(os.getenv("CLUBS_FRONTEND_DIR") or Path(__file__).resolve().parents[2] / "frontend").resolve()


@asynccontextmanager
async def lifespan(app):
    problems = settings.validate_for_startup(DB_PATH)
    if problems:
        raise RuntimeError("Небезопасная конфигурация production:\n - " + "\n - ".join(problems))
    prepare_database()
    from .services import client_logs, mdns
    client_logs.cleanup()
    import asyncio

    async def _daily():
        while True:
            await asyncio.sleep(24 * 3600)
            try:
                client_logs.cleanup()
            except Exception:  # noqa: BLE001 — фоновая уборка не должна ронять сервер
                pass
    daily = asyncio.create_task(_daily())
    zc = mdns.start() if settings.mdns_enabled() else None
    try:
        yield
    finally:
        daily.cancel()
        mdns.stop(zc)


app = FastAPI(
    title="Расписание кружков",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled() else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled() else None,
)

app.add_middleware(GZipMiddleware, minimum_size=800)
if settings.allowed_hosts():
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts())
if settings.cors_origins():
    # Только Bearer (без cookie): allow_credentials=False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        allow_credentials=False,
        max_age=600,
    )
app.middleware("http")(request_pipeline)

app.include_router(public.router)
app.include_router(admin.router)
app.include_router(push.router)
app.include_router(distribution.router)
app.include_router(announcements.router)
app.include_router(app_api.router)


@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok", "mode": "application"}


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness: процесс жив."""
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readyz():
    """Readiness: БД отвечает и схема на актуальной миграции."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        current, head = current_revision(), head_revision()
    except Exception as exc:  # noqa: BLE001
        log.error("readyz failed: %s", exc)
        return JSONResponse({"status": "unavailable"}, status_code=503)
    if current != head:
        return JSONResponse({"status": "migration-pending", "current": current, "head": head}, status_code=503)
    return {"status": "ready", "revision": current}


@app.get("/install", include_in_schema=False)
def install_page():
    """Страница-инструкция «как установить на телефон» (iOS/Android)."""
    page = FRONTEND / "install.html"
    if not page.exists():
        raise HTTPException(404)
    return FileResponse(page)


# исключаем чужие апи в теле http запроса
@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
def unknown_api(path: str):
    raise HTTPException(404, "API-маршрут не найден")


class SiteFiles(StaticFiles):
    """Статика без служебного: тесты/моки/исходники не отдаём (SEC-09); кэш — по типу файла (API-08)."""

    HIDDEN_PREFIXES = ("tests/", "node_modules/")
    HIDDEN_FILES = {"mock-data.json"}

    async def get_response(self, path, scope):
        norm = path.replace("\\", "/").lstrip("/")
        if norm.startswith(self.HIDDEN_PREFIXES) or norm in self.HIDDEN_FILES or norm.endswith((".test.mjs", ".map")):
            raise HTTPException(404)
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            if norm.endswith((".woff2", ".ttf", ".png", ".svg", ".ico")):
                response.headers["Cache-Control"] = "public, max-age=604800"
            else:
                response.headers["Cache-Control"] = "no-cache"  # всегда ревалидация по ETag
            if norm == "sw.js":
                response.headers["Service-Worker-Allowed"] = "/"
        return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/") or request.url.path in {"/healthz", "/readyz"}:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
    if exc.status_code == 404:
        page = FRONTEND / "404.html"
        if page.exists():
            return FileResponse(page, status_code=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


app.mount("/", SiteFiles(directory=FRONTEND, html=True), name="frontend")
