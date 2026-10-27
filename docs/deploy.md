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

## Push в APK через FCM (необязательно)
Без настройки FCM выключен молча: APK получает объявления и переносы опросом (до ~30 мин задержки), Web Push работает как раньше.
Ключ — JSON сервисного аккаунта Firebase (проект `kipclub-9ebd8`, включён Firebase Cloud Messaging API v1). **Это секрет**: не класть в репозиторий и не в образ (в `.gitignore`: `fcm-key*.json`, `*service-account*.json`).

Вариант A (Docker Compose):
1. Скопировать ключ на сервер рядом с `docker-compose.yml`, например `/opt/clubs/secrets/fcm.json`; права: `chown root:10001 fcm.json && chmod 640 fcm.json` (приложение работает под uid 10001).
2. В `docker-compose.yml` у сервиса `app` добавить в `volumes:` строку
   `- ./secrets/fcm.json:/run/secrets/fcm.json:ro`
3. В `.env`: `FCM_CREDENTIALS_FILE=/run/secrets/fcm.json` (project_id берётся из ключа; переопределить — `FCM_PROJECT_ID`).
4. `docker compose up -d --build` (новая зависимость `google-auth` и миграция `0007` с таблицей `app_devices` применяются при старте).

Вариант B (systemd): ключ в `/etc/clubs/fcm.json` (владелец root, группа пользователя сервиса, `640`), в `/etc/clubs/clubs.env` — `FCM_CREDENTIALS_FILE=/etc/clubs/fcm.json`, `systemctl restart clubs`.

Проверка: в админке «Рассылки» → охват показывает «FCM: N» (N — установки APK с FCM, открывавшие приложение за 60 дней); после отправки в журнале рассылок `fcm_sent`. Ошибки — в логе `clubs.fcm` / `clubs.delivery`; токены с ответом UNREGISTERED/404 удаляются автоматически.

## Обновление с миграциями (schedule v2: 0010–0012)
1. `tools/ops/backup.sh pre-migrate` — запомнить путь файла.
2. `git pull --ff-only && docker compose up -d --build` — миграции применяются при старте.
3. `curl -fsS https://<домен>/readyz` и `docker compose exec -T app python -c "from backend.app.migrations import current_revision,head_revision;print(current_revision(),head_revision())"`.
4. Если что-то не так: `git checkout <прошлый коммит> && tools/ops/restore.sh <файл из п.1> --yes && docker compose up -d --build`.

## Проверка после выкатки
`curl -fsS https://<домен>/readyz`; открыть `/`, `/admin/login.html`; `/docs` → 404; заголовки (`curl -I`): CSP, HSTS.

**Что здесь проверено, а что нет:** конфигурация production протестирована локально (старт, Host-проверка, заголовки, `/docs` 404, `/readyz`); `docker build`, `docker compose` и Caddy в песочнице разработки **не запускались** (нет Docker) — первый запуск на сервере считай приёмочным.
