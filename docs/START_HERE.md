# Начало работы с шаблоном

Стек: Python 3.10+ / FastAPI / SQLAlchemy 2 / Pydantic 2 / SQLite; frontend — HTML/CSS/JavaScript без React, TypeScript и npm.
Это каркас, а не готовое приложение. Данные вымышленные. API возвращает 501 для незавершённых функций. Авторизация закрывает доступ (401), не имитирует успешный вход.

## Запуск из корня проекта в PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
.\.venv\Scripts\python.exe server.py
```

Открыть http://127.0.0.1:8000/ . Документация API: http://127.0.0.1:8000/docs . Остановить Ctrl+C.
Активация venv не требуется. Не открывать HTML двойным кликом: JS-модули и fetch требуют сервера.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Пропущенные тесты — задания команды, а не выполненные проверки. SQLite создаётся в backend/development.sqlite3; таблиц пока нет. Локальную БД не коммитить.

## Что уже работает

Единый сервер страниц и API, healthcheck, соединение SQLite, простые страницы, чтение явно включённых моков, минимальные инфраструктурные тесты. Главная показывает фиксированную тестовую неделю 12–17 октября 2026.

## Где выполнять задачи

1. Артём / Илья: backend/app/database.py, models/, main.py. Импортировать модели в init_db перед create_all.
2. Максим Григорьев / Валерий / Надежда: data/sample-data.json и backend/scripts/seed.py.
3. Елисей / Михаил / Сергей Бурдов: backend/app/routers/public.py; DTO в schemas/ по согласованному контракту.
4. Эдик / Максим Филиппенков: backend/app/services/conflicts.py.
5. Фёдор: backend/app/services/schedule.py.
6. Кира / Милена: макеты в docs/design/; общие стили согласовать с Данилой.
7. Алиса / Данила: frontend публичные страницы, css/, js/. Не писать повторно алгоритм расписания.
8. Алина: frontend/admin/, css/admin.css, js/admin/.
9. Алиса Жукова: backend/tests/ бизнес-тесты, заменить явные skip после реализации.
10. Алёна / Виктория: docs/qa-public.md.
11. Кристина / Валерия: docs/qa-admin.md и проверка примеров данных.
12. Кирилл / Артём: routers/admin.py, scripts/create_admin.py, будущий модуль серверных сессий.

Никаких заглушек «успешного сохранения» в настоящем API. Не ловить NotImplementedError с возвратом успеха. Публичная HTML-оболочка админки допустима: защищаться должны данные и операции на сервере.

## Моки и подключение API

Источник — data/sample-data.json. Для браузера копия frontend/mock-data.json (только вымышленные публичные данные). После изменения синхронизировать копию командой:

```powershell
Copy-Item data/sample-data.json frontend/mock-data.json
```

Не публиковать пароли, реальные личные данные и рабочую БД. USE_MOCKS в frontend/js/api.js сейчас true. После реализации нужных API установить false. Ошибки API показывать пользователю; не подменять настоящие данные моками незаметно.

Готовые события schedule_events — пример ответа сервиса; sessions и session_exceptions — его вход. Моки не вычисляют неделю самостоятельно.

## Общие файлы

main.py и database.py — Артём; models/ — Илья с Артёмом; js/api.js — Алиса; css/common.css — Данила с Миленой; общий формат — docs/api-contract.md. Согласовать изменения общих файлов и новых зависимостей. README оставляем без изменений.

## Зависимости

requirements.lock.txt фиксирует проверенные версии для одинакового окружения команды. requirements.txt задаёт допустимые диапазоны; обновлять lock согласованно после проверки.

