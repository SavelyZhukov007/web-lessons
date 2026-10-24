# FEATURE_README — что в патче и как это поставить

Патч `feature.patch` (или готовое дерево `feature.zip`) превращает `web-lessons` из «публичное расписание + заглушка админки» в сервис, который можно выкатывать: настоящая админка, JWT-авторизация, Web Push, тёмная тема, Android-приложение, сборки одной командой.

Рядом: [`docs/DEPLOY_COLLEGE.md`](docs/DEPLOY_COLLEGE.md) (выкатка в колледже, приоритеты и статусы), [`docs/PROD_STATUS.md`](docs/PROD_STATUS.md) (все 74 пункта из `PROD_READINESS.md`: сделано / частично / нет), [`docs/UX_REPORT.md`](docs/UX_REPORT.md) (UX-разбор), [`docs/ANDROID_APK.md`](docs/ANDROID_APK.md) (подробно про APK).

## Что внутри
- **Бэкенд** (FastAPI + SQLite, Python 3.10+): Alembic-миграции 0001–0003; JWT access (15 мин) + refresh с ротацией (повтор старого refresh после окна 10 с отзывает сессию); лимит входа в БД; scrypt; CSRF по Origin; строгий CSP; TrustedHost; аудит-лог; `/healthz`, `/readyz`; проверка конфликтов (кабинет/руководитель) под блокировкой записи.
- **Web Push** (VAPID, `pywebpush`): подписка на кружок, фоновая отправка при отмене/переносе.
- **Сайт**: страницы кружков и расписания, админка (hash-SPA: кружки, занятия, отмены/переносы, справочники, аккаунт), общий диалог **Настройки** на каждой странице (тема система/светлая/тёмная, акцент, размер текста), платформенный вид (Material 3 на Android, iOS-стиль на iPhone), шрифты локально.
- **CLI `server.py`**: `serve`, `build`, `admin`, `seed`, `backup`, `verify-backup`, `check-config`.
- **Android** (`android/`, Capacitor 8): адрес сервера задаётся в приложении.
- **Деплой**: `Dockerfile`, `docker-compose.yml`, `deploy/` (Caddy, systemd, бэкап-таймер), CI-workflow, документация в `docs/`.

## Как поставить на Windows (PowerShell 5)
Вариант 1 — патч (нужен git: `git apply`; программы `patch` в Windows нет):
```powershell
cd C:\Project\ITC\web-lessons
git apply --check C:\path\to\feature.patch      # сухая проверка
git apply --whitespace=nowarn C:\path\to\feature.patch
```
Вариант 2 — просто взять дерево: распакуй `feature.zip` (внутри папка `web-lessons-feature/`; в ней нет секретов, БД, venv, node_modules) и работай из неё или скопируй поверх репозитория. Старые `index.html`, `schedule.ics` в корне и `development.sqlite3` при копировании поверх удали руками — патч их удаляет (кроме sqlite).
> Патч в git-формате (с бинарными файлами: шрифты, иконки), поэтому применять именно `git apply` (GNU `patch` бинарные куски не возьмёт). Проверено на Linux: `git apply --check` на чистой копии `proj` проходит, после применения дерево идентично `feature` (1 безобидное предупреждение про пробелы). На Windows и с CRLF-окончаниями строк я НЕ проверял — если `git apply` ругается, используй `feature.zip`.

Окружение (Python 3.10.4 подходит):
```powershell
cd C:\Project\ITC\web-lessons
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1                       # если запрещены скрипты: Set-ExecutionPolicy -Scope Process Bypass
pip install -r backend\requirements.lock.txt
python server.py admin create admin                # спросит пароль (≥ 10 символов); или $env:ADMIN_PASSWORD='...'
python server.py seed                              # демо-данные (по желанию)
python server.py                                   # http://127.0.0.1:8000  (админка: /admin/login.html)
```
**Первый запуск:** публичной регистрации нет — админа создаёт только `server.py admin create`. Секрет JWT создаётся сам при первом старте в `jwt_secret.key` (в `.gitignore`); для прода задай `JWT_SECRET` (≥ 32 символов).
**Push / VAPID:** ключи генерируются автоматически при первом использовании в `vapid_keys.json` (или путь в `VAPID_KEYS_FILE`; приватный ключ можно дать через `VAPID_PRIVATE_KEY`). Файл не коммить и **бэкапь** — потеряешь ключ, все подписки перестанут работать. В dev push работает только на `localhost`/HTTPS.

## Сборки: `python server.py build <цель>`
| Цель | Результат |
|---|---|
| `web` | `builds\web\` — статический сайт (штамп service worker, без тестов) |
| `pwa` | `builds\pwa\` — установимое PWA (манифест, иконки, apple-touch-icon; `ios` — псевдоним) |
| `android` | `builds\android\clubs-schedule-debug.apk` + `.sha256` |
| `back` | `builds\back\clubs-backend\` и `clubs-backend.zip` — релиз бэкенда (код, миграции, lock, готовый сайт, deploy, `RUN.md`) |
| `all` | всё перечисленное |

`builds/` в `.gitignore`. Параметры: `--out DIR` (web/pwa/back), `--server-url http://IP:PORT` (адрес сервера по умолчанию в APK), `--install` (adb install), `--check-only` (проверить окружение).

### APK на Windows
```powershell
python server.py build android --check-only        # покажет, что найдено (JDK 21+, SDK, Node 22+)
python server.py build android --server-url http://192.168.1.50:8000
```
Скрипт сам ищет JDK 21+ (в том числе `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`) и SDK (`C:\Users\savel\AppData\Local\Android\Sdk`); `JAVA_HOME` выставляется **только на время сборки**, системный JDK 17 не трогается. Явно: `cd android; .\build-apk.ps1 -JavaHome "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot" -SdkRoot "C:\Users\savel\AppData\Local\Android\Sdk"`. Нужны `platforms;android-36` и build-tools 36.0.0 (у тебя есть; если чего-то нет — флаг `-InstallSdkPackages`). Первая сборка — минуты. Если на телефоне уже стоит APK с другим debug-ключом: `adb uninstall ru.kipfin.clubs`.

## Тесты
```powershell
pip install -r backend\requirements-dev.lock.txt
python -m pytest backend tools                     # 207 тестов
node --test frontend\tests\*.test.mjs              # 42 теста (тема, контраст WCAG, даты, push)
playwright install chromium; python -m pytest e2e  # 19 e2e (Chrome)
cd android; npm install; node scripts\prepare-web.mjs; python tests\run_shim_tests.py   # 31 проверка веб-слоя приложения
```
(`node --test` с маской в PowerShell: если не раскрывает `*`, передай файлы по одному.)

## Что проверено, а что НЕТ
**Проверено у меня (Linux-песочница):** бэкенд 207 тестов на Python 3.10 и 3.13 (покрытие 94 %); Node 42; e2e 19 (включая 360/390 px без горизонтального скролла, вход, refresh, тёмная тема, конфликты); shim приложения 31/31; `ruff` чисто; `pip-audit` чисто; все цели `build` отработали; **APK собран** на JDK 21 (Gradle 8.14.3, Capacitor 8.5.3, compileSdk 36); релиз `build back` распакован и запущен на Python 3.10 (readyz, seed, логин); ключевые скриншоты — `/workspace/itc/shots/key/`.
**НЕ проверено:**
- сборка APK и запуск `server.py` на **твоём Windows** (PowerShell 5, Node 24) — только Linux;
- работа приложения на эмуляторе/телефоне: APK установился на софт-эмулятор, но UI на устройстве прогнать не удалось (эмулятор без KVM деградировал);
- доставка Web Push на реальные устройства (в т. ч. iPhone);
- `docker build` / `docker compose` / Caddy / systemd, CI на GitHub, восстановление бэкапа на чистой машине;
- реальный IP клиента за прокси, лимит тела 1 МБ на живом Caddy;
- axe/Lighthouse, ручной QA на реальных телефонах, 40 параллельных занятий в сетке;
- `git apply` патча на Windows.

**Решения владельца, оставленные открытыми:** учебный период/каникулы (DOM-01), публичность контакта руководителя (SEC-07), LICENSE.
Остановить dev-сервер: `Ctrl+C` в окне `python server.py`.
