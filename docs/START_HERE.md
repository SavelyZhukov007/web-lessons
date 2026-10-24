# Быстрый старт

Полная инструкция — в `README.md` (раздел «Быстрый запуск»). Кратко:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.lock.txt   # Windows: .venv\Scripts\pip
./.venv/bin/python server.py admin create admin      # пароль ≥ 10 символов
./.venv/bin/python server.py seed                    # демо-данные (по желанию)
./.venv/bin/python server.py                         # http://127.0.0.1:8000
```

Что где: `docs/api-contract.md` (API), `docs/security.md`, `docs/database.md`, `docs/conflicts.md`, `docs/deploy.md` + `docs/DEPLOY_COLLEGE.md`, `docs/runbook.md`, `docs/qa-checklist.md` (ручная проверка).
Открытые вопросы: `docs/domain-term.md` (учебный период/каникулы).
