# API-контракт (актуальный)

Источник истины — OpenAPI (`/docs` в dev; в production отключён, `ENABLE_DOCS=true` включает). Этот файл — человекочитаемая сводка.

Учебные периоды, повторения, несколько руководителей и аудиторий, импорт и экспорт: [academic-schedule.md](academic-schedule.md).

## Общие правила
- ID — `integer`; дата `YYYY-MM-DD`; время `HH:MM` (24 ч, занятия 08:00–21:00, начало раньше конца); `weekday` — `1..6` (1 = понедельник … 6 = суббота, воскресных занятий нет).
- Все ошибки — JSON с ключом `detail`, но **тип `detail` зависит от кода**:

| Код | `detail` | Когда |
|---|---|---|
| 401 | строка | нет/просрочена сессия админа, неверный логин/пароль |
| 403 | строка | CSRF-проверка Origin не пройдена (запись по cookie с чужого Origin) |
| 404 | строка | сущность/маршрут не найден (`/api/*` неизвестный → «API-маршрут не найден») |
| 409 | **объект** `{code:"CONFLICT", message, conflicts:[{event_id, club_name, date, start_time, end_time, room_name, leader_name, reasons:["room"\|"leader"]}]}` для пересечения расписания; **строка** для нарушения уникальности/внешнего ключа |
| 422 | строка (наши проверки) или **массив** ошибок Pydantic (`[{loc, msg, type}]`) | валидация |
| 429 | строка + заголовок `Retry-After` | лимит входа (5 неудач / 15 мин на пару IP+логин), лимит push-подписок на устройство |
| 503 | `{"status": …}` | `/readyz`: БД недоступна или миграции не применены |

Фронтенд (`js/api.js`, `js/admin/api.js`) сводит все формы к одному `ApiError{status, message, detail}`.

## Служебные
- `GET /healthz` — процесс жив. `GET /readyz` — БД отвечает и ревизия Alembic = head. `GET /api/health` — совместимость.
- `GET /install` — страница установки PWA. `GET /robots.txt`, `/favicon.ico`, `/manifest.webmanifest`, `/sw.js`.

## Публичные
- `GET /api/categories`; `GET /api/rooms`.
- `GET /api/leaders` — только руководители **активных** кружков, **без** поля `contact` (SEC-07).
- `GET /api/clubs?search=&category_id=` — только активные; поиск регистронезависимый (в т. ч. кириллица), `%`/`_` — обычные символы.
- `GET /api/clubs/{id}` — `category`, `leader` (с `contact`), `sessions`, `upcoming_exceptions`.
- `GET /api/clubs/{id}/calendar.ics?week=YYYY-MM-DD` — снимок недели кружка с исключениями, без бесконечного повторения; не подписной календарь. `?start=&end=` — диапазон до 93 дней; `?from=&to=` (или без параметров — от сегодня до конца периода, ≥ 26 недель, ≤ 400 дней). Отменённые даты не попадают, переносы — по новой дате. Правила — `PRODUCT_RULES.md`.
- Schedule v2 (подробно — `docs/schedule-v2-contract.md`): `GET /api/week?week=` (неделя + период, чётность, неучебные дни), `GET /api/sessions/{id}/occurrences`, `GET /api/clubs/{id}/occurrences`, `GET /api/calendar.ics`, `GET /api/sessions/{id}/calendar.ics`. В `GET /api/clubs/{id}` у занятий есть `repeat`, `repeat_label`, `next_dates`.
- `GET /api/schedule?week=YYYY-MM-DD[&category_id&weekday&leader_id&room_id&search]` — `week` — **понедельник**, диапазон 2000-01-03…2100-12-27, иначе 422. Ответ — массив `ScheduleEvent` (`schemas/contracts.py`); `status`: `scheduled|cancelled|moved`; `event_id` = `session_id:original_date`.

## Web Push (публичные, без авторизации)
- `GET /api/push/vapid-public-key` → `{publicKey}`.
- `POST /api/push/subscribe` `{endpoint, keys:{p256dh,auth}, club_id?}` → 201 `subscribed` / 200 `already-subscribed` (идемпотентно). `endpoint` — только из списка push-сервисов (иначе 422); не более N подписок на устройство (429).
- `POST /api/push/unsubscribe` `{endpoint, club_id?}`; `POST /api/push/status` `{endpoint, club_id?}`.
- `POST /api/push/preferences` `{endpoint, announcements}` — получать ли объявления этим браузером (переносы/отмены не затрагивает).
- `POST /api/app/devices` `{device_id, token|null, platform:"android", app_version, club_ids[], announcements, changes}` → 204 — регистрация FCM-токена установки APK (публичный, ограничение частоты по IP и устройству, 429).
- `GET /api/announcements?since=<id>&clubs=<id,id>&device=<id установки>&off=0|1` → `{items:[{id,title,body,url,created_at}], last_id}` — объявления за 14 дней для APK (не более 20).

## Рассылки (админ)
- `GET /api/admin/broadcasts?limit=50` — журнал. `POST /api/admin/broadcasts/estimate` `{audience:"all"|"clubs", club_ids, session_ids}` → `{web, apk}`.
- `POST /api/admin/broadcasts` `{title≤80, body≤500, url?, audience, club_ids, session_ids, idempotency_key}` → 201; тот же ключ → 200 `duplicate:true`; тот же текст тем же админом за 2 минуты → 409.
- Отправка — фоновая задача после отмены/переноса; ошибки отправки не влияют на ответ API; «мёртвые» подписки (404/410) удаляются.

## Админские (`/api/admin/*`)
Авторизация: cookie `admin_session` (HttpOnly, SameSite=Lax, Secure в production) **или** `Authorization: Bearer <access_token>` (токен возвращает `login`; Bearer приоритетнее cookie). Запись по cookie требует совпадения `Origin`/`Host` (или `TRUSTED_ORIGINS`).

- `POST /login` `{login, password}` → `{admin, access_token, refresh_token, token_type:"bearer", expires_in, refresh_expires_in}` + cookies `admin_session` и `admin_refresh` (path `/api/admin/refresh`). `POST /refresh` (refresh из cookie или `{refresh_token}`) → новая пара в том же формате; старый refresh отзывается; повтор старого: 409 в пределах `REFRESH_GRACE_SECONDS`, позже 401 + отзыв сессии; невалидный → 401. Access живёт `ACCESS_MINUTES` (15). `POST /logout` → 204. `GET /status` → 200 с данными админа или 401, если не авторизован (используется фронтом как проверка сессии). `POST /password` `{current_password, new_password}` → 204; текущая сессия сохраняется, остальные отзываются.
- CRUD: `categories` (цвет `#RRGGBB` обязателен), `leaders`, `rooms`, `clubs`, `sessions` — `GET|POST /…`, `PATCH|DELETE /…/{id}`. Удаление записи, на которую есть ссылки → 409.
- Schedule v2: `GET /conflicts` (отчёт), `GET|POST /conflicts/overrides`, `DELETE /conflicts/overrides/{id}`; `POST /import/publish?dry_run&prune` (пакетный JSON), `GET /import/publishes`, `POST /import/publishes/{id}/rollback`. Публикация черновика `POST /imports/{id}/publish` делает бэкап и возвращает `publish_id` для отката.
- Исключения: `GET /exceptions`, `POST /exceptions/cancellations`, `POST /exceptions/moves`, `PATCH|DELETE /exceptions/{id}`.

Формы исключений:
```json
{"session_id": 1, "original_date": "2026-10-13", "type": "cancelled", "comment": "Праздничный день"}
{"session_id": 1, "original_date": "2026-10-20", "type": "moved", "new_date": "2026-10-22",
 "new_start_time": "17:00", "new_end_time": "18:00", "new_room_id": 2, "comment": "Перенос на вечер"}
```
Правила: `original_date` должна выпадать на день недели занятия; перенос на воскресенье запрещён (422); одно исключение на пару `(session_id, original_date)`; перенос «в прошлое» **разрешён** (журнал можно править задним числом — решение зафиксировано в `PROD_STATUS.md`). Конфликты — `docs/conflicts.md`.
