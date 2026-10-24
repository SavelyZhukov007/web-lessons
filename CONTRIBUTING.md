# Как вносить изменения

1. Ветка от `main`: `feature/<коротко>` или `fix/<коротко>`. Прямых коммитов в `main` нет — только PR с зелёным CI и ревью.
2. Окружение: `python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.lock.txt` (Windows: `.venv\Scripts\pip`).
3. Перед PR: `ruff check .`, `pytest`, `node --test frontend/tests/*.test.mjs` (e2e: `playwright install chromium && pytest e2e`).
4. Изменения схемы БД — только через Alembic (`backend/migrations`), с тестом.
5. Секреты, `*.sqlite3`, `jwt_secret.key`, `vapid_keys.json` в репозиторий не попадают (см. `.gitignore`).
6. Фронтенд без inline-скриптов и inline-стилей — действует строгий CSP (`script-src 'self'; style-src 'self'`).
