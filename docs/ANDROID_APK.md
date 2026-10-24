# Android-приложение «Кружки КИПФИН» — как собрать и поставить debug APK

> TL;DR: **Capacitor 8** оборачивает собранный сайт (`frontend/`), поверх — маленький shim: при первом запуске приложение
> спрашивает адрес сервера `http://IP:PORT` (его можно сменить потом в окне «Настройки → Сервер»), все `/api/…` уходят на этот
> сервер. Сборка одной командой из корня репозитория: **`python server.py build android`** (или `npm run apk` / `.\build-apk.ps1` в `android/`).
> Результат: `builds/android/clubs-schedule-debug.apk` (+ `.sha256`).

## 0. Что реально проверено (честно)

| Что | Статус |
|---|---|
| Debug APK собран **в моей песочнице (Linux)**: JDK 21, Node 22, Android SDK 36, Gradle 8.14.3, Capacitor 8.5.3, compileSdk/targetSdk 36, minSdk 24 | ✅ `builds/android/clubs-schedule-debug.apk`, 4 404 259 байт, sha256 `bb34fe6825121de7162ea0b956033a5b6598677f50ba7beb8e0ea8315cb80ac8` |
| Веб-слой приложения (shim: нормализация адреса, «Проверить соединение», диалог настроек с блоком «Сервер», `APP_DEFAULT_SERVER`, вход админа по Bearer, **ротация refresh-токена**) — Playwright против живого сервера | ✅ 31/31 (`android/tests/run_shim_tests.py`) |
| Установка APK и запуск UI на эмуляторе Android 14 | см. §7 |
| Сборка на **твоём Windows** (PowerShell 5, JDK 21.0.12 в `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`, SDK 36 / build-tools 35 и 36) | ❌ **не проверялась** — у меня Linux. Автоопределение JDK/SDK под Windows написано по документации путей, но на Windows не запускалось |
| Release/подписанный APK, Google Play, нативные push (FCM) | ❌ не делалось |

## 1. Почему Capacitor
PWA/TWA требует HTTPS и домен, а у колледжа сервер может быть просто `http://192.168.x.x:8000`. Голый WebView — ручная работа с адресом. Capacitor даёт cleartext HTTP на LAN, нативный HTTP-слой (`CapacitorHttp`: запросы идут мимо CORS WebView), сплэш/иконки и расширение плагинами позже.

**Авторизация админа в приложении — Bearer, не cookie.** Страница живёт на origin `http://localhost`, сервер — на другом, cookie между ними не ходят. Поэтому приложение (`window.AppServer` есть) хранит access- и refresh-токены в `localStorage` WebView и шлёт `Authorization: Bearer`. Access живёт 15 минут; при 401 клиент один раз вызывает `POST /api/admin/refresh` с `refresh_token` (single-flight), получает **новую пару** и повторяет запрос. В браузере всё наоборот — HttpOnly-cookie, JS токенов не видит. Компромисс приложения: токен в `localStorage` WebView доступен коду страницы (XSS-риск снижен строгим CSP, но не исключён).

## 2. Что внутри `android/`
```
android/
  package.json / package-lock.json   npm-скрипты: apk, prepare-web, apk:release-check, test:web
  capacitor.config.json              appId ru.kipfin.clubs, cleartext, CapacitorHttp
  build-apk.ps1                      Windows-обёртка: -ServerUrl -JavaHome -SdkRoot -Install -InstallSdkPackages -CheckOnly
  scripts/env.mjs                    автоопределение JDK 21+ и Android SDK (Windows/Linux/macOS)
  scripts/prepare-web.mjs            frontend/ → www/ : убирает sw/manifest/install, подмешивает shim; пишет default-server.js, если задан APP_DEFAULT_SERVER
  scripts/patch-android.mjs          cleartext + network_security_config (идемпотентно)
  scripts/build-apk.mjs              проверки → npm ci → prepare-web → cap sync → gradlew assembleDebug → dist/*.apk
  shim/app-shim.js                   AppServer: адрес сервера, префикс /api/, Bearer
  shim/server-setup.js, settings.html  экран первого запуска «Сервер»
  tests/run_shim_tests.py            Playwright-тесты веб-слоя (31 проверка)
  tests/device_test.py               смоук на эмуляторе/телефоне через CDP (adb forward)
```
Общий диалог «Настройки» сайта (тема система/светлая/тёмная, акцент, размер текста) в приложении получает ещё и раздел **«Сервер»** (проверить / изменить / забыть адрес).

## 3. Предусловия на Windows
1. **Node.js 22+** (у тебя 24 — подходит).
2. **JDK 21+**. Capacitor 8 / AGP 8.13 на JDK 17 не собираются. Скрипт сам ищет JDK 21+ в: `JAVA_HOME` (если ≥ 21), `JDK_21_HOME`, `C:\Program Files\Eclipse Adoptium\jdk-21*` (**твой `jdk-21.0.12.101-hotspot` подпадает**), Microsoft/Zulu/Corretto/Java, `%LOCALAPPDATA%\Programs`, `~\.jdks`, `jbr` из Android Studio. Найденный JDK подставляется в `JAVA_HOME` и `PATH` **только для процесса сборки** — системный JDK 17 и переменные окружения не меняются. Если нужно указать явно: `-JavaHome "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"`.
3. **Android SDK**: у тебя `C:\Users\savel\AppData\Local\Android\Sdk` (определяется автоматически: `ANDROID_HOME` → `ANDROID_SDK_ROOT` → `%LOCALAPPDATA%\Android\Sdk`). Нужны `platforms;android-36`, `platform-tools`, `build-tools` (у тебя 35.0.0 и 36.0.0 — для compileSdk 36 Gradle использует 36.0.0; недостающее он докачает сам при принятых лицензиях; можно `-InstallSdkPackages`).
4. Интернет при первой сборке (npm + Gradle ~ сотни МБ).
5. Python 3.10 нужен только для `python server.py build android` (оркестратор) — сам по себе APK собирается и `npm run apk`.

## 4. Команды (PowerShell 5)
Из корня репозитория:
```powershell
python server.py build android                                      # → builds\android\clubs-schedule-debug.apk
python server.py build android --server-url http://192.168.1.50:8000   # адрес зашит по умолчанию (в приложении его всё равно можно сменить)
python server.py build android --install                            # + adb install -r и запуск на подключённом устройстве
python server.py build android --check-only                         # только проверить JDK/SDK/Node, ничего не собирать
```
Или напрямую из `android\`:
```powershell
cd android
npm install
npm run apk
powershell -ExecutionPolicy Bypass -File .\build-apk.ps1 -ServerUrl http://192.168.1.50:8000 -Install
powershell -ExecutionPolicy Bypass -File .\build-apk.ps1 -CheckOnly
```
`--server-url` / `-ServerUrl` кладёт адрес в `APP_DEFAULT_SERVER` → `www/js/default-server.js`. Приоритет в приложении: сохранённый пользователем адрес → `APP_DEFAULT_SERVER` → экран первого запуска. Первая сборка — минуты, повторные — секунды.

### Сервер для телефона
```powershell
$env:ADMIN_PASSWORD = '<пароль ≥10 символов>'; python server.py admin create admin
python server.py serve --host 0.0.0.0 --port 8000       # dev-режим, в сети только на время теста
ipconfig                                                  # IPv4 ПК, например 192.168.1.50
New-NetFirewallRule -DisplayName "Clubs 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private   # от администратора
```
Телефон и ПК — в одной сети (не «гостевой» с изоляцией клиентов). В приложении: `192.168.1.50:8000`. Для боевого сервера — HTTPS-домен (`docs/DEPLOY_COLLEGE.md`); тогда cleartext в приложении не нужен.
Учти: в `ENV=production` запросы с неизвестным `Host` отклоняются (`ALLOWED_HOSTS`) — добавь туда адрес, по которому приложение ходит.

### Установка на телефон
1. Телефон: «Настройки → О телефоне» 7 раз по «Номер сборки» → «Для разработчиков» → «Отладка по USB». Подключить, принять RSA-ключ.
2. ```powershell
   adb devices                                  # должен быть "device"
   adb install -r builds\android\clubs-schedule-debug.apk
   adb shell monkey -p ru.kipfin.clubs -c android.intent.category.LAUNCHER 1
   ```
   Если уже стоит APK, подписанный **другим** debug-ключом (например, собранный на другой машине), `install -r` даст `INSTALL_FAILED_UPDATE_INCOMPATIBLE` — сначала `adb uninstall ru.kipfin.clubs` (настройки приложения сбросятся).
3. Эмулятор: хост виден как `http://10.0.2.2:PORT`. Отладка WebView — `chrome://inspect`.

## 5. Тесты
```
. toolchain/env.sh                                        # Linux; на Windows — Node 22+, Python с playwright
node android/scripts/prepare-web.mjs
SHOTS_DIR=/tmp/apkshots python android/tests/run_shim_tests.py        # 31 проверка веб-слоя
python android/tests/device_test.py                       # на запущенном эмуляторе/телефоне (нужен websocket-client)
```

## 6. Что проверяют тесты веб-слоя (31/31)
Нормализация адреса (в т. ч. мусор/порт), «Проверить соединение» (ок/ошибка/недоступен), редирект на экран сервера при первом запуске, `APP_DEFAULT_SERVER`, смена/забывание сервера, кнопка ⚙ и диалог настроек на каждой странице, вход админа по Bearer (токены в `localStorage`), ротация refresh (старый токен перестаёт работать, новый — работает), все запросы идут на выбранный сервер.

## 7. Эмулятор Android 14 (AVD `t34`, `-accel off`)
Эмулятор шёл **без аппаратного ускорения** (в песочнице нет KVM), поэтому очень медленный.
* ✅ Холодная загрузка ОС (`sys.boot_completed=1`) и `adb install -r builds/android/clubs-schedule-debug.apk` → **`Success`** (для этой версии APK; предыдущая сборка тоже ставилась).
* ❌ **UI, экран «Сервер», настройки и админ-вход на устройстве НЕ проверены.** Попытка прогнать `tests/device_test.py` на текущей сборке не завершилась: на софт-эмуляторе система деградировала (load average в госте > 30, `Can't find service: window`, чёрный скриншот, WebView-devtools-сокет не появился за 3 минуты). Это ограничение окружения, а не доказанный дефект приложения — но и доказательства работы на устройстве у меня нет.
* Вместо этого веб-слой приложения (тот же `www/`, тот же shim) проверен Playwright-ом: 31/31 (§6).
* `tests/device_test.py` обновлён под Bearer/refresh/настройки (вход через форму, ротация refresh, тёмная тема в диалоге) и **ни разу не проходил до конца** — запусти у себя на эмуляторе с WHPX/HAXM или на телефоне.

## 8. Известные ограничения
* APK подписан debug-ключом (не для Play); release — отдельный keystore и `assembleRelease`.
* Push на телефон из приложения (FCM) не сделан — только Web Push в браузере/PWA.
* Cleartext HTTP включён ради LAN-теста; для боевого сервера — HTTPS.
* `npm audit` показывает уязвимости в build-time зависимостях (Capacitor CLI) — в APK они не попадают.
* Иконка/сплэш — стандартные Capacitor.
