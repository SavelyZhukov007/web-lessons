# Runbook (эксплуатация)

Все команды — из каталога приложения (`/opt/clubs` для systemd; в Docker: `docker compose exec app …`). Конфигурация — `deploy/.env.example`.

## Деплой и откат
**Docker:** `git pull && docker compose up -d --build`. Миграции БД применяются при старте приложения. Проверка: `curl -fsS https://<домен>/readyz`.
**Откат:** `git checkout <прошлый-тег> && docker compose up -d --build`. Если новая версия применила миграцию — **сначала** восстанови БД из бэкапа, сделанного перед обновлением (миграции «вниз» не гарантируются).
**Перед каждым обновлением:** `server.py backup` (см. ниже).
**systemd:** `git pull && .venv/bin/pip install -r backend/requirements.lock.txt && .venv/bin/python server.py build web && sudo systemctl restart clubs`.

## Первый запуск
1. `cp deploy/.env.example .env`, задать `SITE_ADDRESS`, `ALLOWED_HOSTS`, `JWT_SECRET` (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).
2. `docker compose up -d --build`.
3. Создать админа: `docker compose exec -e ADMIN_PASSWORD='<пароль ≥ 10 символов>' app python server.py admin create admin` (или интерактивно без `-e`). Пароль не вписывать в историю shell: можно `read -s ADMIN_PASSWORD; export ADMIN_PASSWORD`, `docker compose exec -e ADMIN_PASSWORD app …`.
4. (демо) `docker compose exec app python server.py seed`.

## Админы
- Список: `server.py admin list`. Сброс пароля: `server.py admin reset-password LOGIN` (все сессии админа отзываются).
- Забыт пароль единственного админа — тот же `reset-password` на сервере.

## Бэкап и восстановление
- Бэкап: `server.py backup --dir /backups --keep 14` (в Docker том `clubs-backups`; systemd-таймер `clubs-backup.timer` — каждый день 03:30).
- Проверка: `server.py verify-backup /backups/<файл>.sqlite3.gz` — делай регулярно, а не только в аварии.
- Восстановление: остановить приложение → распаковать копию (`gunzip -c … > /data/clubs.sqlite3`; удалить старые `-wal/-shm`) → запустить → `/readyz`.
- Копию держи **вне** сервера (другой диск/облако) — копия на том же диске не защищает от потери диска.

## Логи
- Приложение пишет JSON-логи в stdout (`docker compose logs -f app`; `journalctl -u clubs`). В логе есть `request_id`; 500 возвращает его пользователю — по нему ищи запись. Пароли и токены в лог не попадают.
- Журнал действий админа: поток `clubs.audit` (+ файл `AUDIT_LOG_FILE`, если задан).
- Ротация: Docker — `logging: {driver: json-file, options: {max-size: 10m, max-file: "5"}}` или journald; для файла аудита — `logrotate`.

## Что делать, если…
| Симптом | Действия |
|---|---|
| Сайт не открывается | `docker compose ps`; `logs app`; `curl localhost:8000/readyz` внутри хоста; проверить диск (`df -h`) и сертификат Caddy (`logs caddy`) |
| `/readyz` = 503 `migration-pending` | приложение запущено со старой БД: перезапуск применит миграции; если падает — смотри лог, восстанови БД из бэкапа |
| Приложение не стартует в production | `server.py check-config` — перечислит проблемы конфигурации |
| «Слишком много попыток входа» (429) | подождать окно (15 мин) или проверить, не подбирают ли пароль (в аудите `login_failed`); сброс: `reset-password` |
| Админ видит 401 после перезапуска | `JWT_SECRET` изменился (задан иначе) — войти заново; секрет хранить постоянно |
| Диск заполнен | уменьшить `--keep`, очистить старые бэкапы/логи; БД растёт медленно |
| Push не приходит | `GET /api/push/vapid-public-key` отвечает? HTTPS есть? На iOS сайт должен быть установлен «На экран Домой» (iOS 16.4+) |

## Масштабирование
Один воркер (SQLite + блокировка записи в процессе). Для нескольких экземпляров нужен PostgreSQL — см. `docs/database.md`.
