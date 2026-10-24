# Безопасность

## Аутентификация администратора
- Публичной регистрации нет. Администраторов создаёт оператор: `python server.py admin create LOGIN` (пароль ≥ 10 символов, из stdin/env/запроса; не из аргументов CLI). Сброс — `admin reset-password` (все сессии отзываются).
- Пароль хранится как `scrypt` (рехеш при входе, если параметры устарели). Проверка логина выполняется за постоянное время (фиктивный хеш для несуществующего логина).
- Вход выдаёт **JWT (HS256, PyJWT)** с `sid` (id серверной сессии) и `jti`. Сервер хранит в `admin_sessions` только `sha256(jti)`; токен валиден, пока жива строка сессии → logout/смена пароля/сброс реально отзывают доступ. Срок — `SESSION_HOURS` (по умолчанию 168 ч). Просроченные сессии удаляются при входе.
- **Access + refresh с ротацией.** Access JWT живёт `ACCESS_MINUTES` (по умолчанию 15 мин) и привязан к `jti` текущей пары. Refresh — непрозрачный токен `<sid>.<секрет>`; в БД лежит только `sha256`. `POST /api/admin/refresh` при каждом вызове выдаёт **новую пару** (старый refresh и старый access перестают работать). Повтор уже использованного refresh: в пределах `REFRESH_GRACE_SECONDS` (10 с; гонка двух вкладок) → 409 без отзыва, позже → **сессия отзывается** целиком (событие аудита `refresh_reuse_detected`). Срок скользящий: `SESSION_HOURS` отсчитывается от последнего refresh. Refresh-cookie `admin_refresh` — `HttpOnly`, `SameSite=Strict`, `path=/api/admin/refresh` (на остальные запросы не отправляется).
- Транспорт токена: cookie `admin_session` (`HttpOnly`, `SameSite=Lax`, `Secure` в production) или `Authorization: Bearer` (для приложения Android). В браузере токен не доступен JS и не лежит в `localStorage`; в приложении Capacitor Bearer хранится в `localStorage` WebView (особенность режима «приложение»).
- Лимит входа: 5 неудач за 15 минут на пару IP+логин, хранится в БД (переживает рестарт, не растёт неограниченно), ответ 429 + `Retry-After`.
- `JWT_SECRET` ≥ 32 символов из env, либо файл `JWT_SECRET_FILE` (создаётся один раз, права 600, в `.gitignore`).

## Защита запросов
- CSRF: запись (POST/PUT/PATCH/DELETE) с cookie требует `Origin`/`Referer`, совпадающего с Host или с `TRUSTED_ORIGINS`; запросы с `Authorization: Bearer` не используют cookie и не подвержены CSRF.
- Заголовки: строгий CSP (`script-src 'self'; style-src 'self'` — **без inline-скриптов и стилей**, поэтому `theme-init.js` — внешний блокирующий скрипт), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `COOP`; HSTS — в production.
- `TrustedHostMiddleware` по `ALLOWED_HOSTS`; `/docs`, `/redoc`, `/openapi.json` в production выключены.
- Ограничения входных данных (длины строк: 120/300/4000 символов по типу поля, диапазоны чисел; лимит размера всего тела запроса на уровне приложения не ставится — `request_body max_size 1MB` настроен в `deploy/Caddyfile` (не проверялось на живом Caddy)), параметризованные запросы SQLAlchemy, вывод пользовательских данных во фронтенде через `textContent`/DOM-API (не `innerHTML`).
- Статика не отдаёт служебное: `tests/`, `*.test.mjs`, `*.map`.
- Публичный `/api/leaders` не содержит контактов; контакт руководителя виден на странице его **активного** кружка (решение о публичности контактов — за владельцем продукта).

## Web Push
- Приватный VAPID-ключ — в `VAPID_PRIVATE_KEY` или `VAPID_KEYS_FILE` (создаётся один раз, в `.gitignore`). Подписки принимаются только от известных push-сервисов (защита от SSRF через `endpoint`).

## Конфигурация production
`ENV=production` без валидной конфигурации → приложение не стартует (`python server.py check-config` покажет причины): Secure-cookie, `JWT_SECRET`, `ALLOWED_HOSTS` без `*`, БД вне каталога приложения, `ENABLE_DOCS` выключен.

## Зависимости
`pip-audit -r backend/requirements.lock.txt` — без известных уязвимостей на 23.10.2026; проверка включена в CI.

## Аудит
Логгер `clubs.audit`, одна JSON-строка на событие: `login_ok/login_failed/login_blocked`, `token_refreshed`, `refresh_reuse_detected`, `password_changed`, `admin_write` (метод, путь, статус, admin_id, `request_id`); пароли и токены не логируются. Файл — `AUDIT_LOG_FILE`.

## Производительность хеширования
`scrypt` (N=2^16, r=8, p=1, 64 МиБ): ≈160 мс на хеш и ≈150 мс на проверку на машине разработки (Linux, 1 поток); на железе колледжа не измерялось.

## Не покрыто
Внешний аудит/пентест не проводился; MFA и ограничение числа одновременных сессий не реализованы; журнал действий админа пишется в лог/файл, но не показывается в UI.
