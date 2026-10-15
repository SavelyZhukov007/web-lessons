# Структура базы данных

Рабочая SQLite-база хранится в файле `development.sqlite3` в корне проекта. Таблицы создаются автоматически при старте FastAPI-приложения или при запуске служебных скриптов.

## Таблицы

| Таблица | Назначение | Ключевые поля |
| --- | --- | --- |
| `admins` | Учётные записи администраторов | `login`, `password_hash` |
| `admin_sessions` | Серверные cookie-сессии администраторов | `admin_id`, `token_hash`, `expires_at` |
| `categories` | Направления кружков | `name`, `color` |
| `leaders` | Руководители кружков | `name`, `position`, `contact` |
| `rooms` | Аудитории | `name`, `building`, `capacity` |
| `clubs` | Кружки | `name`, `description`, `category_id`, `leader_id`, `is_active` |
| `sessions` | Регулярные занятия | `club_id`, `room_id`, `weekday`, `start_time`, `end_time` |
| `session_exceptions` | Отмены и переносы конкретных занятий | `session_id`, `original_date`, `type`, `new_*`, `comment` |

## Связи и ограничения

- `clubs.category_id -> categories.id`
- `clubs.leader_id -> leaders.id`
- `sessions.club_id -> clubs.id`
- `sessions.room_id -> rooms.id`
- `session_exceptions.session_id -> sessions.id`
- `session_exceptions.new_room_id -> rooms.id`

Дополнительные ограничения:

- `rooms` уникальны по паре `(name, building)`;
- `sessions.weekday` ограничен диапазоном `1..6`;
- в `sessions` и переносах из `session_exceptions` время начала должно быть раньше времени окончания;
- в `session_exceptions` действует уникальность `(session_id, original_date)` — для одного occurrence может существовать только одно исключение;
- удаление кружка каскадно удаляет его регулярные занятия и исключения, но удаление направления, руководителя и аудитории блокируется, пока есть связанные записи.
