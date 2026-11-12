# KipClub — расписание кружков колледжа

Веб-приложение с публичным расписанием, административной панелью, PWA и Android-клиентом. Текущая версия исходников указана в [version.json](version.json); Android `versionCode` и последний идентификатор сборки — в [android/version.json](android/version.json). Эти файлы описывают рабочую копию, а не подтверждают, какая версия развернута на сервере.

## Возможности

- Публичный каталог кружков и недельное расписание с поиском и фильтрами.
- Учебные периоды, недельные/чётные/нечётные/разовые занятия, неучебные дни, отмены и переносы.
- Админ-панель для расписания и справочников, импорта DOCX/XLSX, проверки конфликтов, журналирования изменений и рассылок.
- Экспорт расписания в календарь; административный экспорт и печать.
- Личное расписание и уведомления; Web Push для браузера/PWA и опциональный FCM для Android.
- Установка как PWA и Android-приложение с офлайн-возможностями, виджетами и системными настройками.
- Резервное копирование SQLite и проверка восстановления из резервной копии.

В приложении две роли: гость и администратор. Публичной регистрации нет; учётные записи администраторов создаются оператором. Подробности и ограничения собраны в [документации](docs/README.md).

## Быстрый запуск

Нужны Python 3.10+ и pip. Все команды выполняются из корня репозитория.

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\.venv\Scripts\python.exe server.py admin create admin
.\.venv\Scripts\python.exe server.py seed
.\.venv\Scripts\python.exe server.py
```

Создание администратора запросит пароль. Загрузка демо-данных необязательна. Сервер разработки слушает `http://127.0.0.1:8000`; админ-панель доступна по адресу `http://127.0.0.1:8000/admin/login.html`. Не открывайте HTML-файлы напрямую с диска.

### Linux / macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements.lock.txt
./.venv/bin/python server.py admin create admin
./.venv/bin/python server.py seed
./.venv/bin/python server.py
```

По умолчанию локальная база — `development.sqlite3` в корне проекта. При запуске приложение применяет миграции Alembic. Настройка production-окружения и безопасное хранение секретов описаны в [deploy/.env.example](deploy/.env.example) и [руководстве по развёртыванию](docs/deploy.md).

## Основные команды

Справка CLI: `python server.py --help`.

| Команда | Назначение |
|---|---|
| `python server.py` | Локальный сервер разработки с перезагрузкой |
| `python server.py serve --host HOST --port PORT` | Явный запуск сервера |
| `python server.py build web\|pwa\|android\|back\|all` | Сборка сайта, PWA, APK, backend-пакета или всех целей |
| `python server.py admin create\|reset-password\|list` | Управление администраторами |
| `python server.py seed [--dry-run]` | Загрузка демо-данных |
| `python server.py backup` / `verify-backup FILE` / `restore FILE --yes` | Резервная копия, проверка и восстановление SQLite |
| `python server.py check-config` | Проверка production-конфигурации |

Для сборки Android нужны Node.js 22+, JDK 21+ и Android SDK. Подробная инструкция и ограничения проверки сборки: [docs/ANDROID_APK.md](docs/ANDROID_APK.md).

## Проверки

Установите инструменты разработки из lock-файла:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.lock.txt
```

Затем запустите проверки:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
node --test frontend/tests/*.test.mjs
```

Браузерные E2E-тесты находятся в `e2e/` и запускаются отдельно после установки Chromium для Playwright: `.\.venv\Scripts\python.exe -m playwright install chromium`, затем `.\.venv\Scripts\python.exe -m pytest e2e`. В Linux/macOS используйте `./.venv/bin/python -m ...`. Тесты Android и PWA описаны в [docs/ANDROID_APK.md](docs/ANDROID_APK.md).

## Структура проекта

| Каталог / файл | Назначение |
|---|---|
| `backend/app/` | FastAPI, модели, маршруты, бизнес-логика и настройки |
| `backend/migrations/` | Миграции Alembic |
| `backend/tests/` | Backend- и миграционные тесты |
| `frontend/` | Сайт, админ-панель, CSS, PWA и браузерные тесты |
| `android/` | Capacitor-клиент, нативные функции и сборка APK |
| `e2e/` | Playwright E2E-тесты |
| `deploy/` | Docker, Caddy, systemd и пример конфигурации |
| `docs/` | Руководства, контракты и датированные отчёты |

## Документация

Начните с [индекса документации](docs/README.md). Он отделяет актуальные руководства и контракты от исторических отчётов. В частности:

- [Быстрый старт](docs/START_HERE.md)
- [Правила продукта](docs/PRODUCT_RULES.md)
- [Контракт API](docs/api-contract.md) и [контракт расписания v2](docs/schedule-v2-contract.md)
- [База данных](docs/database.md), [безопасность](docs/security.md) и [конфликты расписания](docs/conflicts.md)
- [Развёртывание](docs/deploy.md), [инструкция для колледжа](docs/DEPLOY_COLLEGE.md) и [эксплуатационный runbook](docs/runbook.md)
