"""Служебные эндпоинты приложения: опознание сервера (/api/app/info) и журнал ошибок клиентов (/api/logs, «Логи» в админке)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import settings
from ..database import get_db
from ..services import broadcast as broadcast_service
from ..services import client_logs
from ..services import stats as stats_service
from .admin import require_admin

router = APIRouter(tags=["app"])
APP_ID = "itc-kruzhki"
API_VERSION = 1
SERVER_VERSION = "0.2.0"


def server_id() -> str:
    """Стабильный обезличенный id сервера (по секрету подписи — сам секрет из него не восстановить)."""
    return hashlib.sha256(b"server-id|" + settings.jwt_secret().encode()).hexdigest()[:16]


@router.get("/api/app/info")
def app_info():
    return JSONResponse({"app": APP_ID, "name": settings.server_name(), "version": SERVER_VERSION,
                         "api_version": API_VERSION, "server_id": server_id()}, headers={"Cache-Control": "no-cache"})


@router.post("/api/logs", status_code=202)
async def post_logs(request: Request):
    raw = await request.body()
    if len(raw) > client_logs.MAX_BODY:
        raise HTTPException(413, "Слишком большой пакет логов")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(422, "Ожидался JSON") from None
    if not isinstance(body, dict) or not isinstance(body.get("entries"), list):
        raise HTTPException(422, "Ожидалось {device, version, entries: [...]}")
    device = str(body.get("device") or "")[:64]
    ip = request.client.host if request.client else "-"
    if not client_logs.allow("ip:" + ip) or (device and not client_logs.allow("dev:" + device)):
        raise HTTPException(429, "Слишком часто")
    meta = {k: body.get(k) for k in ("device", "version", "platform", "os", "webview")}
    entries = [e for e in (client_logs.normalize(x, meta) for x in body["entries"][: client_logs.MAX_ENTRIES]) if e]
    return {"accepted": client_logs.append(entries)}


class DeviceIn(BaseModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    token: str | None = Field(None, max_length=512)
    platform: str = Field("android", pattern=r"^(android)$")
    app_version: str = Field("", max_length=32)
    club_ids: list[int] = Field(default_factory=list, max_length=100)
    announcements: bool = True
    changes: bool = True

    @field_validator("token")
    @classmethod
    def _token(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not re.fullmatch(r"[A-Za-z0-9_:\-]{20,512}", v):
            raise ValueError("Некорректный токен")
        return v

    @field_validator("app_version")
    @classmethod
    def _ver(cls, v: str) -> str:
        return re.sub(r"[^0-9A-Za-z.+_-]", "", v)


@router.post("/api/app/devices", status_code=204)
def register_device(body: DeviceIn, request: Request, db: Session = Depends(get_db)):
    """Регистрация установки APK для FCM (токен, «мои кружки», переключатели). Публичный, с ограничением частоты."""
    ip = request.client.host if request.client else "-"
    if not client_logs.allow("devreg-ip:" + ip) or not client_logs.allow("devreg:" + body.device_id):
        raise HTTPException(429, "Слишком часто")
    clubs = sorted({c for c in body.club_ids if 0 < c < 10**9})
    broadcast_service.register_device(db, body.device_id, body.token, body.platform, body.app_version,
                                      clubs, body.announcements, body.changes)


def _filters(level, version, device, date_from, date_to):
    try:
        return dict(level=level, version=version or None, device=device or None,
                    date_from=date.fromisoformat(date_from) if date_from else None, date_to=date.fromisoformat(date_to) if date_to else None)
    except ValueError:
        raise HTTPException(422, "Даты в формате YYYY-MM-DD") from None


@router.get("/api/admin/logs")
def admin_logs(level: str | None = Query(None), version: str | None = Query(None), device: str | None = Query(None),
               date_from: str | None = Query(None), date_to: str | None = Query(None), limit: int = Query(300, ge=1, le=5000),
               _admin=Depends(require_admin)):
    items = client_logs.query(limit=limit, **_filters(level, version, device, date_from, date_to))
    return {"items": items, "versions": sorted({e.get("version", "") for e in items if e.get("version")}),
            "retention_days": settings.logs_retention_days()}


@router.get("/api/admin/logs.txt")
def admin_logs_txt(level: str | None = Query(None), version: str | None = Query(None), device: str | None = Query(None),
                   date_from: str | None = Query(None), date_to: str | None = Query(None), _admin=Depends(require_admin)):
    items = client_logs.query(limit=20000, **_filters(level, version, device, date_from, date_to))
    return PlainTextResponse(client_logs.as_text(items), headers={
        "Content-Disposition": 'attachment; filename="itc-logs.txt"', "Cache-Control": "no-store"})


class PingIn(BaseModel):
    install_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    kind: str = Field("web", pattern=r"^(web|ios-pwa|pwa)$")


@router.post("/api/app/ping", status_code=204)
def app_ping(body: PingIn, request: Request, db: Session = Depends(get_db)):
    """Обезличенный «я пользуюсь»: сайт / PWA раз в день и при возврате. Хранится только хэш id, без IP/UA."""
    if "kipclub-stress" in request.headers.get("user-agent", "").lower():
        return  # нагрузочный тест не считаем
    ip = request.client.host if request.client else "-"
    if not client_logs.allow("ping-ip:" + ip) or not client_logs.allow("ping:" + body.install_id):
        raise HTTPException(429, "Слишком часто")
    stats_service.ping(db, body.install_id, body.kind)


@router.get("/api/admin/stats")
def admin_stats(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return stats_service.summary(db)
