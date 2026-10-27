# Schedule v2 — контракт общего ядра поверх T1–T4

Описывает то, что реально реализовано. Модель данных и правила дат — T1/T2 (`docs/academic-schedule.md`),
импорт — T3, отображение — T4. Ядро (occurrence_source, конфликты, .ics, уведомления, журнал импорта)
только читает их данные и не меняет их правил.

## 1. Миграции

| № | Поток | Содержимое |
|---|-------|------------|
| 0010 | T1 | `academic_periods`, `no_class_days`, `sessions.period_id`, `sessions.repeat` |
| 0011 | T2 | rooms: `building`/`capacity` nullable, `is_remote`, `remote_url`, `remote_instructions`; `club_leaders`, `session_leaders`, `session_rooms` |
| 0012 | T3 | `import_drafts` |
| —    | ядро | миграций нет: разрешения конфликтов и журнал публикаций — JSON рядом с БД/бэкапами |

## 2. Данные (как в моделях T1/T2)

```
academic_periods(id, name, start_date, end_date, even_week_start)  -- понедельник ЧЁТНОЙ недели
no_class_days(id, period_id FK CASCADE, date, reason)   UNIQUE(period_id, date)
sessions.period_id NULL, sessions.repeat 'weekly'|'even'|'odd'|'once' (one_off_date важнее repeat)
rooms.is_remote, remote_url, remote_instructions
club_leaders(club_id, leader_id)      -- доп. руководители; основной — clubs.leader_id
session_leaders(session_id, leader_id) -- если есть, ЗАМЕНЯЕТ список кружка для занятия
session_rooms(session_id, room_id)     -- доп. аудитории; основная — sessions.room_id (первая)
```
Даты — `YYYY-MM-DD`, время — `HH:MM`, полуинтервал `[start, end)`.

Правило дня — `services/occurrences.original_occurs(session, day, period, holidays)` (T1):
занятие без периода идёт бессрочно; с периодом — только внутри `[start_date, end_date]`, не в
неучебные дни этого периода; even/odd — по чётности относительно `even_week_start`.

## 3. Occurrences (Python)

Единая точка ядра: `backend/app/services/occurrence_source.py`.

```python
iter_occurrences(db, session|session_id, date_from, date_to) -> list[Occurrence]
Occurrence(date, start, end, room_ids, leader_ids,
           status: 'scheduled'|'moved_in'|'moved_out'|'cancelled',
           source_session_id, exception_id, original_date, club_id,
           parity: 'odd'|'even'|None, comment, original_start, original_end, group_ids)
Occurrence.key == f"{session_id}:{original_date}"   # = event_id недели, стабильный UID
Occurrence.occupies  -> status in {scheduled, moved_in}
```
Базовые даты серии берёт провайдер `_T1Provider`: он загружает периоды/неучебные дни и для каждой
даты вызывает `original_occurs` T1 — правила не дублируются. Исключения (отмена/перенос) ядро
применяет само, как `services/schedule.build_week`. `week_events()` совпадает с `build_week` по
полям v1 и T2 (`room_ids`, `room_names` «аудитория · корпус», `leader_ids`, `leader_names`,
`occupied_room_ids`, `is_remote`, `repeat`, `period_id`) и добавляет `parity`.
Без модуля T1 работает встроенный fallback (`set_provider()` — подмена в тестах).

Ресурсы (как `ClubSession.room_ids/leader_ids`, `Club.leader_ids`): ведущие — `session_leaders`,
иначе `clubs.leader_id` + `club_leaders`; аудитории — `sessions.room_id` + `session_rooms`;
дистанционная аудитория (`is_remote`) не участвует в конфликтах по аудитории, ведущие — участвуют.

## 4. REST

| Метод | Ответ |
|-------|-------|
| `GET /api/schedule?week=` | `ScheduleEvent[]` (как раньше) + `parity, room_ids, leader_ids, room_names, leader_names` |
| `GET /api/week?week=&…фильтры` | `{week_start, week_end, parity, period:{id,title,starts_on,ends_on}\|null, no_class:[{date,title}], events: ScheduleEvent[]}` |
| `GET /api/sessions/{id}/occurrences?from&to` | `{session_id, club_id, repeat, repeat_label, from, to, items:[{key,date,start,end,status,session_id,club_id,room_ids,leader_ids,exception_id,original_date,parity,comment}]}` |
| `GET /api/clubs/{id}/occurrences?from&to&limit` | `{club_id, from, to, next_dates:[date×5], items:[…как выше]}` |
| `GET /api/clubs/{id}` | `sessions[]` += `repeat, repeat_label, next_dates[≤3]` |
| `GET /api/calendar.ics?from&to&club_id=…` | все активные кружки |
| `GET /api/clubs/{id}/calendar.ics[?week= \| ?from&to]` | кружок; `week` — старый режим одной недели |
| `GET /api/sessions/{id}/calendar.ics?from&to` | одна серия |
| `GET /api/admin/conflicts?from&to&include_allowed` | `{from,to,items:[conflict+allowed],overrides}` |
| `GET/POST /api/admin/conflicts/overrides`, `DELETE …/{id}` | разрешить совместное занятие `{session_a, session_b, date?, comment}` |
| `POST /api/admin/import/publish?dry_run&prune` | тело — набор §5; `{dry_run, stats, publish:{id,backup,…}}`; 422/409 `{code:"IMPORT_REJECTED", errors, conflicts}` |
| `GET /api/admin/import/publishes`, `POST …/{id}/rollback` | журнал и откат к бэкапу перед публикацией |

Окно по умолчанию: сегодня (МСК) … max(конец текущего периода, +26 недель); максимум 400 дней.
`repeat_label`: «каждую неделю» / «по чётным неделям» / «по нечётным неделям» / «разово ДД.ММ.ГГГГ».

**409 конфликта** (admin create/update session, перенос, правка/удаление исключения, клуб):
`{code:"CONFLICT", message, conflicts:[{event_id, club_name, date, start_time, end_time, room_name,
leader_name, reasons:[room|leader|group], resource, resource_id, resource_label, session_id,
other_session_id, session:{…}, other:{…}, dates:[≤20], dates_total}]}` — одна запись на пару серий,
поля v1 описывают ближайшую дату чужого занятия. Проверяются только **новые** пересечения
(«после» минус «до») в окне по умолчанию ∪ даты самого изменения.

## 5. Импорт

**Черновики T3** (`/api/admin/imports`, DOCX/XLSX → строки → решения → публикация) — основной путь.
Ядро добавляет к `POST /api/admin/imports/{id}/publish` только снимок БД перед записью
(`pre-import-*.sqlite3.gz`) и запись в журнал: ответ получает `publish_id`; откат —
`POST /api/admin/import/publishes/{publish_id}/rollback` (восстанавливается весь снимок).

**Пакетный JSON** (`POST /api/admin/import/publish`) — для скриптов/переноса данных, формат ниже.

```json
{
  "version": 1,
  "rooms":   [{"building": "Главный", "number": "201", "capacity": 30, "is_remote": false, "link": null /* → rooms.remote_url */}],
  "leaders": [{"full_name": "Петров Пётр Петрович", "position": "", "contact": ""}],
  "clubs": [{
    "name": "Робототехника", "category": "Техника", "category_color": "#2563eb",
    "description": "", "is_active": true,
    "leaders": ["Петров Пётр Петрович"],
    "sessions": [
      {"repeat": "weekly|even|odd", "period_id": 1, "weekday": 1, "start": "10:00", "end": "11:30",
       "rooms": [{"building": "Главный", "number": "201"}], "leaders": ["…необязательно"]},
      {"repeat": "once", "date": "2026-11-11", "start": "12:00", "end": "13:00", "rooms": [ … ]}
    ]
  }]
}
```
Сопоставление (идемпотентность): кружок — нормализованное название (регистр, ё/е, кавычки,
пробелы); ведущий — нормализованное ФИО; аудитория — (корпус, номер) → `rooms.building/name`;
категория — название. Серия = (weekday, start, end, первая аудитория, date, repeat).
`prune=true` (по умолчанию): серии кружков из набора, которых нет в наборе, удаляются.
`period_id` — существующий учебный период (для even/odd обязателен). Многие ведущие/аудитории пишутся в таблицы T2,
если они есть. Всё — одна транзакция; перед записью — бэкап `pre-import-*.sqlite3.gz`.
