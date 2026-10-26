# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.lock.txt backend/requirements.lock.txt
RUN pip install -r backend/requirements.lock.txt

COPY backend backend
COPY frontend frontend
COPY pwa pwa
COPY android/shim android/shim
COPY tools tools
COPY data data
COPY server.py pyproject.toml version.json ./
# Продовая сборка фронта = сборка PWA: в обычной вкладке сайт как прежде, в установленном PWA (standalone)
# — та же оболочка, что в APK. Хэш сборки в service worker, без тестов/служебных файлов
RUN python server.py build pwa --out /app/builds/web

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir -p /data /backups && chown app:app /data /backups
USER app

ENV ENV=production \
    CLUBS_SCHEDULE_DB_PATH=/data/clubs.sqlite3 \
    CLUBS_FRONTEND_DIR=/app/builds/web \
    JWT_SECRET_FILE=/data/jwt_secret.key \
    VAPID_KEYS_FILE=/data/vapid_keys.json \
    APP_LOGS_DIR=/data/client-logs \
    APP_RELEASES_DIR=/data/releases/android \
    FORWARDED_ALLOW_IPS=*
VOLUME ["/data", "/backups"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; h=os.environ['ALLOWED_HOSTS'].split(',')[0].strip(); r=urllib.request.Request('http://127.0.0.1:8000/readyz',headers={'Host':h}); urllib.request.urlopen(r,timeout=4)"
# ОДИН воркер: SQLite + блокировка записи в процессе (см. docs/runbook.md)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
