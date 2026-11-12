# Android-приложение «KipClub» — как собрать и поставить debug APK

> TL;DR: **Capacitor 8** оборачивает собранный сайт (`frontend/`), поверх — shim: при первом запуске приложение
> спрашивает адрес сервера `http://IP:PORT` (его можно сменить потом в окне «Настройки → Сервер»), все `/api/…` уходят на этот
> сервер. Debug-сборка запускается из корня командой **`python server.py build android`** или напрямую через `npm run apk` в `android/`.
> Результат оркестратора — APK в `android/dist/`; версия и точный путь печатаются в выводе. Версионированный пакет собирается отдельно через `node android/scripts/build.mjs --version v1.9.022pr --platform android --no-bump` (пример для версии из текущего `version.json`). Форматы каналов и стадий описаны там же. Добавляйте `--release` только для подписанной сборки с настроенным ключом.

## 0. Статус проверок

Сведения ниже собраны в разные даты и не означают, что APK из текущей рабочей копии уже собран или выпущен. Для исходников текущая версия и Android `versionCode` указаны в [version.json](../version.json) и [android/version.json](../android/version.json); история последней зафиксированной проверки устройства — в [отчёте 1.9.021](final-release-19021.md).

| Что | Статус |
|---|---|
| Node-тесты Android shim | Команда `cd android; npm run test:web`; актуальный результат зависит от проверяемой версии |
| APK на эмуляторе/устройстве | Проверяйте отдельно; исторические ограничения окружения описаны в §7 и отчёте 1.9.021 |
| Сборка на Windows и подписанный release APK | Эта инструкция не подтверждает такую сборку; проверьте на целевой машине и с release-keystore |
| FCM | Интеграция и серверная отправка покрываются тестами; получение push на физическом устройстве требует приёмочного теста с production-конфигурацией |

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
  tests/*.test.mjs                   node-тесты шима (версии, адрес сервера, офлайн, сессия админа)
  tests/device_test.py               смоук на эмуляторе/телефоне через CDP (adb forward)
```
Общий диалог «Настройки» сайта (тема система/светлая/тёмная, акцент, размер текста) в приложении получает ещё и раздел **«Сервер»** (проверить / изменить / забыть адрес).

## 3. Предусловия на Windows
1. **Node.js 22+**.
2. **JDK 21+**. Capacitor 8 / AGP 8.13 требуют JDK 21. Скрипт ищет подходящий JDK в `JAVA_HOME`, `JDK_21_HOME` и стандартных каталогах распространённых дистрибутивов/Android Studio. Если нужно указать явно, передайте `-JavaHome "C:\путь\к\jdk-21"`; найденный JDK применяется только для процесса сборки.
3. **Android SDK**: задайте `ANDROID_HOME` или `ANDROID_SDK_ROOT` либо используйте стандартный каталог SDK пользователя. Нужны `platforms;android-36`, `platform-tools` и подходящая версия `build-tools`; недостающие пакеты скрипт может установить при принятых лицензиях (`-InstallSdkPackages`).
4. Интернет при первой сборке (npm + Gradle ~ сотни МБ).
5. Python 3.10 нужен только для `python server.py build android` (оркестратор) — сам по себе APK собирается и `npm run apk`.

## 4. Команды (PowerShell 5)
Из корня репозитория:
```powershell
python server.py build android                                      # → путь APK будет выведен; debug APK находится в android\dist\
python server.py build android --server-url http://192.168.1.50:8000   # адрес зашит по умолчанию (в приложении его всё равно можно сменить)
python server.py build android --install                            # + adb install -r и запуск на подключённом устройстве
python server.py build android --check-only                         # только проверить JDK/SDK/Node, ничего не собирать
```
Или напрямую из `android\`:
```powershell
cd android
npm ci
npm run apk
powershell -ExecutionPolicy Bypass -File .\build-apk.ps1 -ServerUrl http://192.168.1.50:8000 -Install
powershell -ExecutionPolicy Bypass -File .\build-apk.ps1 -CheckOnly
```
`--server-url` / `-ServerUrl` кладёт адрес в `APP_DEFAULT_SERVER` → `www/js/default-server.js`. Приоритет в приложении: сохранённый пользователем адрес → `APP_DEFAULT_SERVER` → экран первого запуска. Первая сборка — минуты, повторные — секунды.

### Сервер для телефона
```powershell
python server.py admin create admin                      # пароль будет запрошен в консоли
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
   $apkPath = Read-Host "Введите путь к основному APK из вывода сборки"
   adb install -r $apkPath
   adb shell monkey -p ru.kipfin.clubs -c android.intent.category.LAUNCHER 1
   ```
   Если уже стоит APK, подписанный **другим** debug-ключом (например, собранный на другой машине), `install -r` даст `INSTALL_FAILED_UPDATE_INCOMPATIBLE` — сначала `adb uninstall ru.kipfin.clubs` (настройки приложения сбросятся).
3. Эмулятор: хост виден как `http://10.0.2.2:PORT`. Отладка WebView — `chrome://inspect`.

## 5. Тесты
```
. toolchain/env.sh                                        # Linux; на Windows — Node 22+, Python с playwright
node android/scripts/prepare-web.mjs
(cd android && npm run test:web)                        # node-тесты шима
python pwa/tests/run_pwa_tests.py                         # оболочка в standalone + покрытие pwa/*.js ≥ 90%
python android/tests/device_test.py                       # на запущенном эмуляторе/телефоне (нужен websocket-client)
```

## 6. Историческая проверка веб-слоя (до 1.9.016)
Нормализация адреса (в т. ч. мусор/порт), «Проверить соединение» (ок/ошибка/недоступен), редирект на экран сервера при первом запуске, `APP_DEFAULT_SERVER`, смена/забывание сервера, кнопка ⚙ и диалог настроек на каждой странице, вход админа по Bearer (токены в `localStorage`), ротация refresh (старый токен перестаёт работать, новый — работает), все запросы идут на выбранный сервер.

## 7. Исторический прогон на эмуляторе Android 14 (AVD `t34`, `-accel off`)
Это запись о конкретном старом прогоне, а не актуальный статус устройства. Эмулятор шёл **без аппаратного ускорения** (в песочнице не было KVM), поэтому очень медленный. Позднейшие выборочные физические проверки Android, включая доступность и виджеты, описаны в [отчёте 1.9.021](final-release-19021.md); они также не заменяют полный проход для текущего APK.
* ✅ Для APK той исторической сборки холодная загрузка ОС (`sys.boot_completed=1`) и установка завершились `Success`. Это не проверка APK из текущей рабочей копии.
* ❌ **В том прогоне UI, экран «Сервер», настройки и админ-вход на устройстве не были подтверждены.** Попытка прогнать `tests/device_test.py` не завершилась: на софт-эмуляторе система деградировала (load average в госте > 30, `Can't find service: window`, чёрный скриншот, WebView-devtools-сокет не появился за 3 минуты). Это ограничение окружения, а не доказанный дефект приложения.
* Вместо этого веб-слой приложения (тот же `www/`, тот же shim) проверен Playwright-ом: 31/31 (§6).
* В том окружении `tests/device_test.py` не прошёл до конца; для текущего выпуска повторите его на эмуляторе с аппаратным ускорением или физическом телефоне.

## 8. Известные ограничения
* Debug APK подписывается debug-ключом и не подходит для публикации. Подписанный release APK требует отдельного keystore; наличие подписанного файла нужно проверять для конкретного выпуска.
* Без FCM (сборка без `google-services.json`, демо-сборка, сервер без ключа, телефон без Google Play Services) объявления и переносы приходят опросом — с задержкой до получаса.

## 9. Push через FCM
* **Сборка.** `npm run`/`build-apk.ps1` вызывает `scripts/patch-android.mjs`: если есть `android/google-services.json` с пакетом `ru.kipfin.clubs` и это не демо, он копируется в `android/android/app/`, подключаются `firebase-bom:35.1.0` + `firebase-messaging`, плагин `com.google.gms.google-services`, классы из `native/fcm/` (`ItcMessagingService`, `ItcFcm`) и сервис `MESSAGING_EVENT` в манифесте. Без файла всё это убирается — сборка чистая, без Firebase.
* **`google-services.json` можно коммитить**: это не секрет (идентификаторы проекта и API-ключ клиента, который и так извлекается из любого APK). Секрет — только ключ сервисного аккаунта на сервере (см. `docs/deploy.md`); его в репозиторий не класть.
* **Как работает.** При старте/смене настроек приложение получает FCM-токен и отправляет `POST /api/app/devices` `{device_id, token, platform, app_version, club_ids, announcements, changes}` (повторно — только при изменениях или раз в сутки из SyncWorker). Сервер шлёт только data-сообщения (`type`: `announcement`, `cancel`, `reschedule`, `schedule-change`, `update-available`) с приоритетом HIGH и `collapse_key` события; уведомление рисует приложение в тех же каналах (`itc_changes`, `itc_announcements`).
* **Дедупликация общая с опросом** (`Push.claim`, последние 200 ключей): `a<id>` для объявлений, `c<session>:<дата><kind>` (для переноса + новое время) для изменений — одно событие не покажется дважды, если пришло и по FCM, и при синхронизации. Опрос остаётся резервным путём.
* **Тесты:** `PushTest` (разбор сообщений, ключи = ключам ChangeDetector/Announcements, настройки, dedupe), backend `tests/test_fcm.py`.
* Cleartext HTTP включён ради LAN-теста; для боевого сервера — HTTPS.
* Перед выпуском повторно проверяйте `android/package-lock.json` через `npm audit`. Уязвимость только в build-time зависимости не означает, что код пакета включён в APK, но всё равно требует оценки и решения.
* Launcher-иконки и splash-ресурсы KipClub берутся из `assets/brand/kipclub/android/` и копируются скриптом `patch-android.mjs`.
