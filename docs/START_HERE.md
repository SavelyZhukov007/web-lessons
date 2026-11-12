# Быстрый старт

Полная инструкция и команды для Linux/macOS — в корневом [README.md](../README.md). На Windows откройте PowerShell в корне репозитория:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\.venv\Scripts\python.exe server.py admin create admin
.\.venv\Scripts\python.exe server.py seed
.\.venv\Scripts\python.exe server.py
```

Создание администратора запросит пароль; демо-данные загружать необязательно. Сервер разработки доступен по адресу `http://127.0.0.1:8000`, админ-панель — `http://127.0.0.1:8000/admin/login.html`. Приложение применяет миграции Alembic при запуске.

Ориентиры по документации: [индекс](README.md), [API](api-contract.md), [безопасность](security.md), [база данных](database.md), [конфликты](conflicts.md), [развёртывание](deploy.md) и [runbook](runbook.md). Учебные периоды и импорт описаны в [academic-schedule.md](academic-schedule.md).
