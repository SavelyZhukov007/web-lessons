"""Страницы распространения приложения: /ios (PWA на iPhone), /ios/pwa, /android/ и выдача APK.

APK берётся из каталога релизов (APP_RELEASES_DIR, по умолчанию <repo>/releases/android):
  * если там есть latest.json ({"file": "...apk", "version": "1.2.0", ...}) — отдаём указанный файл;
  * иначе — самый свежий по времени изменения *.apk.
Блок RuStore на /android/ показывается, только когда задан RUSTORE_URL.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .. import settings

router = APIRouter(include_in_schema=False)

APK_MEDIA_TYPE = "application/vnd.android.package-archive"
_ROOT = Path(__file__).resolve().parents[3]
_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)\.apk$", re.I)


def _frontend() -> Path:
    return Path(os.getenv("CLUBS_FRONTEND_DIR") or _ROOT / "frontend").resolve()


def releases_dir() -> Path:
    return Path(os.getenv("APP_RELEASES_DIR") or _ROOT / "releases" / "android").resolve()


def _page(rel: str) -> FileResponse:
    page = _frontend() / rel
    if not page.is_file():
        raise HTTPException(404)
    return FileResponse(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


def _int(v) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def latest_release() -> dict | None:
    """Описание последнего APK или None, если релизов нет."""
    base = releases_dir()
    if not base.is_dir():
        return None
    meta: dict = {}
    apk: Path | None = None
    manifest = base / "latest.json"
    if manifest.is_file():
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            meta = {}
        name = str(meta.get("file") or "")
        candidate = (base / name).resolve() if name else None
        # только файл внутри каталога релизов (никаких ../)
        if candidate and candidate.parent == base and candidate.suffix.lower() == ".apk" and candidate.is_file():
            apk = candidate
    if apk is None:
        found = sorted((p for p in base.glob("*.apk") if p.is_file()), key=lambda p: p.stat().st_mtime)
        if not found:
            return None
        apk = found[-1]
        meta = {}
    stat = apk.stat()
    version = meta.get("version")
    if not version:
        m = _VERSION_RE.search(apk.name)
        version = m.group(1) if m else None
    sha = meta.get("sha256")
    if not sha:
        side = apk.with_name(apk.name + ".sha256")
        sha = side.read_text(encoding="utf-8").split()[0] if side.is_file() else None
    return {
        "path": apk,
        "file": apk.name,
        "version": version,
        "size": stat.st_size,
        "sha256": sha,
        "versionCode": _int(meta.get("versionCode")),
        "changelog": [str(x) for x in meta.get("changelog") or [] if str(x).strip()][:20] if isinstance(meta.get("changelog"), list) else [],
        "minSupported": _int(meta.get("minSupported")),
        "updated": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/ios")
def ios_page():
    return _page("ios/index.html")


@router.get("/ios/")
def ios_slash():
    return RedirectResponse("/ios", status_code=308)


@router.get("/ios/pwa")
def ios_pwa_page():
    return _page("ios/pwa.html")


@router.get("/android")
def android_no_slash():
    return RedirectResponse("/android/", status_code=308)


@router.get("/android/")
def android_page():
    return _page("android/index.html")


# APK по умолчанию раздаётся из GitHub Releases (последний релиз, файл kipclub.apk)
GITHUB_APK_URL = "https://github.com/SavelyZhukov007/web-lessons/releases/latest/download/kipclub.apk"


@router.get("/api/app/android")
def android_info():
    """Метаданные для страницы /android/ и для проверки обновлений внутри приложения.

    Приложение сравнивает versionCode со своим, скачивает url (относительный — от адреса этого ответа),
    сверяет sha256 и size; versionCode установленного приложения ниже minSupported — обновление обязательное.
    APP_DOWNLOAD_URL — внешний адрес APK (например, CDN), APP_MIN_SUPPORTED — переопределяет minSupported из latest.json.
    """
    rel = latest_release()
    url = os.getenv("APP_DOWNLOAD_URL", "").strip()
    url = url if url.startswith("https://") else ("/android/download" if rel else GITHUB_APK_URL)
    data = {"available": rel is not None, "rustore_url": settings.rustore_url(), "download_url": url, "url": url if rel else None}
    if rel:
        data.update({k: rel[k] for k in ("file", "version", "size", "sha256", "updated", "versionCode", "changelog")})
        data["versionName"] = rel["version"]
        env_min = _int(os.getenv("APP_MIN_SUPPORTED"))
        data["minSupported"] = env_min if env_min is not None else rel["minSupported"]
    return JSONResponse(data, headers={"Cache-Control": "no-cache"})


@router.api_route("/android/download", methods=["GET", "HEAD"])
def android_download():
    rel = latest_release()
    if rel is None:
        # локального релиза нет — последний APK из GitHub Releases
        return RedirectResponse(GITHUB_APK_URL, status_code=307, headers={"Cache-Control": "no-cache"})
    return FileResponse(
        rel["path"],
        media_type=APK_MEDIA_TYPE,
        filename=rel["file"],  # → Content-Disposition: attachment; filename="…"
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )

