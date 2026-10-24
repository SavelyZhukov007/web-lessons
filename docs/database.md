# База данных

SQLite (WAL, `foreign_keys=ON`, `busy_timeout`). Путь: `CLUBS_SCHEDULE_DB_PATH` (в production — вне репозитория, том `/data`); по умолчанию dev-файл `development.sqlite3` в корне репозитория (в `.gitignore`).

**Схема управляется Alembic** (`backend/migrations`): `0001` — основная схема, `0002` — push-подписки, сессии/лимитер. При старте приложение применяет миграции (`prepare_database()`); пустая БД и БД, созданная до Alembic, штампуются корректно. Тесты используют `CLUBS_USE_CREATE_ALL=1` (быстро), отдельный тест проверяет цепочку миграций и совпадение со схемой моделей.

| Таблица | Назначение |
|---|---|
| `admins`, `admin_sessions` | администраторы (scrypt-хеш) и серверные сессии (`sha256(jti)`, срок) |
| `login_attempts` | счётчик неудачных входов для лимитера |
| `categories` (цвет обязателен `#RRGGBB`), `leaders`, `rooms` | справочники |
| `clubs` | кружки (`is_active` скрывает кружок) |
| `sessions` | регулярные занятия: `club_id`, `room_id`, `weekday 1..6`, `start_time < end_time` |
| `session_exceptions` | отмены/переносы: уникально `(session_id, original_date)`, поля `new_*` |
| `push_subscriptions` | Web Push: `endpoint`, ключи, `club_id` (NULL = все изменения) |

Ограничения: уникальность `(name, building)` у аудиторий; CHECK на день недели и порядок времени; каскадное удаление кружка → его занятия → исключения; удаление категории/руководителя/аудитории с зависимостями блокируется (409).

## Конкурентность
Запись защищена `asyncio.Lock` внутри процесса (проверка конфликта + commit — одна секция). Поэтому **ровно один воркер** (`--workers 1`). Масштабирование на несколько процессов требует PostgreSQL и блокировок/ограничений уровня БД.

## SQLite или PostgreSQL
Для одного колледжа и десятков одновременных читателей SQLite достаточно (замеры: 240 занятий → ~22 мс на `/api/schedule`). Переход на PostgreSQL нужен при нескольких экземплярах приложения; миграции Alembic это упрощают.

## Бэкапы
`python server.py backup --dir /backups --keep 14` — консистентная копия через sqlite3 backup API, `integrity_check`, gzip, ротация. Проверка: `server.py verify-backup FILE`. Восстановление — `docs/runbook.md`.
