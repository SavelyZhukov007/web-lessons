# Развёртывание

Целевая схема: **Caddy (HTTPS) → uvicorn (1 воркер) → SQLite на томе**. Подробный пошаговый сценарий для колледжа — `docs/DEPLOY_COLLEGE.md`.

## Вариант A: Docker Compose (рекомендуется)
```bash
cp deploy/.env.example .env      # SITE_ADDRESS, ALLOWED_HOSTS, JWT_SECRET, VAPID_SUBJECT
docker compose up -d --build
docker compose exec app python server.py admin create admin
```
- `app` — непривилегированный пользователь (uid 10001), БД/секреты/VAPID на томе `/data`, бэкапы — `/backups`, healthcheck `/readyz`.
- `caddy` — TLS: публичный домен → Let's Encrypt автоматически (нужны порты 80/443 снаружи); внутренний адрес → `CADDY_TLS=tls internal` (сертификат внутреннего CA, его нужно добавить в доверенные на устройствах).
- Данные переживают рестарт/пересборку (именованные тома).

## Вариант B: без Docker (systemd)
Файлы: `deploy/clubs.service`, `clubs-backup.service`, `clubs-backup.timer`. Каталог `/opt/clubs`, venv `.venv`, конфиг `/etc/clubs/clubs.env` (права 600), данные `/var/lib/clubs`. Перед прокси (Caddy/nginx) приложение слушает `127.0.0.1:8000`.

## Обязательные условия
- `ENV=production`; `ALLOWED_HOSTS`; секрет `JWT_SECRET`; HTTPS (cookie `Secure`).
- Один воркер. Не использовать `--reload`.
- Прокси передаёт `X-Forwarded-For/Proto` (Caddy делает это по умолчанию); `FORWARDED_ALLOW_IPS` ограничивает доверие (в Docker-сети — `*`, порт приложения наружу не публикуется).

## Проверка после выкатки
`curl -fsS https://<домен>/readyz`; открыть `/`, `/admin/login.html`; `/docs` → 404; заголовки (`curl -I`): CSP, HSTS.

**Что здесь проверено, а что нет:** конфигурация production протестирована локально (старт, Host-проверка, заголовки, `/docs` 404, `/readyz`); `docker build`, `docker compose` и Caddy в песочнице разработки **не запускались** (нет Docker) — первый запуск на сервере считай приёмочным.
