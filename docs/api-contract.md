# Актуальный API-контракт

## Общие правила

- ID сущностей: `integer`.
- Формат даты: `YYYY-MM-DD`.
- Формат времени: `HH:MM`.
- `weekday`: `1–6` (`1 = понедельник`, `6 = суббота`).
- Неавторизованные запросы к административному API получают `401`.
- Ошибка приложения возвращается в формате `{"detail": "Сообщение"}`.

## Публичные маршруты

- `GET /api/categories`
- `GET /api/leaders`
- `GET /api/rooms`
- `GET /api/clubs?search=...&category_id=...` — только активные кружки
- `GET /api/clubs/{id}` — активный кружок с `category`, `leader`, `sessions`, `upcoming_exceptions`
- `GET /api/schedule?week=2026-10-12[&category_id=...&weekday=...&leader_id=...&room_id=...&search=...]`

`GET /api/schedule` возвращает массив `ScheduleEvent` из `backend/app/schemas/contracts.py`. Для перенесённого занятия `event_id` сохраняет идентификатор исходного occurrence (`session_id:original_date`), а `status` принимает значения `scheduled`, `cancelled` или `moved`.

## Административные маршруты

### Авторизация

- `POST /api/admin/login` — `{login, password}`, устанавливает cookie-сессию
- `POST /api/admin/logout`
- `GET /api/admin/status`

### CRUD-справочники и кружки

- `GET|POST /api/admin/categories`
- `PATCH|DELETE /api/admin/categories/{id}`
- `GET|POST /api/admin/leaders`
- `PATCH|DELETE /api/admin/leaders/{id}`
- `GET|POST /api/admin/rooms`
- `PATCH|DELETE /api/admin/rooms/{id}`
- `GET|POST /api/admin/clubs`
- `PATCH|DELETE /api/admin/clubs/{id}`
- `GET|POST /api/admin/sessions`
- `PATCH|DELETE /api/admin/sessions/{id}`

### Исключения из регулярного расписания

- `GET /api/admin/exceptions`
- `POST /api/admin/exceptions/cancellations`
- `POST /api/admin/exceptions/moves`
- `PATCH /api/admin/exceptions/{id}`
- `DELETE /api/admin/exceptions/{id}`

### Формы исключений

Отмена:

```json
{
  "session_id": 1,
  "original_date": "2026-10-13",
  "type": "cancelled",
  "comment": "Праздничный день"
}
```

Перенос:

```json
{
  "session_id": 1,
  "original_date": "2026-10-20",
  "type": "moved",
  "new_date": "2026-10-22",
  "new_start_time": "17:00",
  "new_end_time": "18:00",
  "new_room_id": 2,
  "comment": "Перенос на вечер"
}
```
