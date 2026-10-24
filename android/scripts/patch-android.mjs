import { readVersion } from './version.mjs';
// Идемпотентно дорабатывает сгенерированный android/ проект: HTTP по LAN (cleartext), network_security_config.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const app = join(root, 'android', 'app', 'src', 'main');
const manifestPath = join(app, 'AndroidManifest.xml');
if (!existsSync(manifestPath)) throw new Error('Нет ' + manifestPath + ' — сначала `npx cap add android`');

mkdirSync(join(app, 'res', 'xml'), { recursive: true });
writeFileSync(join(app, 'res', 'xml', 'network_security_config.xml'), `<?xml version="1.0" encoding="utf-8"?>
<!-- DEBUG/LAN: разрешён http:// к любым хостам (IP:PORT вводит пользователь). Для production — только HTTPS и убрать этот файл. -->
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors><certificates src="system" /></trust-anchors>
    </base-config>
</network-security-config>
`);

let xml = readFileSync(manifestPath, 'utf8');
const set = (attr, val) => {
  const re = new RegExp(`\\s${attr.replace('.', '\\.')}="[^"]*"`);
  xml = re.test(xml) ? xml.replace(re, ` ${attr}="${val}"`) : xml.replace('<application', `<application\n        ${attr}="${val}"`);
};
set('android:usesCleartextTraffic', 'true');
set('android:networkSecurityConfig', '@xml/network_security_config');
if (!xml.includes('android.permission.INTERNET')) xml = xml.replace('</manifest>', '    <uses-permission android:name="android.permission.INTERNET" />\n</manifest>');
// «Добавить в календарь» (@ebarooni/capacitor-calendar): запись событий в календарь устройства, запрос разрешения во время работы
for (const perm of ['READ_CALENDAR', 'WRITE_CALENDAR']) if (!xml.includes('android.permission.' + perm)) xml = xml.replace('</manifest>', `    <uses-permission android:name="android.permission.${perm}" />\n</manifest>`);
// обновление внутри приложения: системный установщик для скачанного APK (тот же ключ → поверх, данные сохраняются)
if (!xml.includes('REQUEST_INSTALL_PACKAGES')) xml = xml.replace('</manifest>', '    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />\n</manifest>');
if (!xml.includes('ACCESS_NETWORK_STATE')) xml = xml.replace('</manifest>', '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n</manifest>');
writeFileSync(manifestPath, xml);
console.log('[patch-android] manifest: cleartext + networkSecurityConfig OK');

// Цвета фона для светлой/тёмной темы системы (окно до загрузки WebView и системный сплэш не «вспыхивают» белым ночью)
const values = join(app, 'res', 'values'); const valuesNight = join(app, 'res', 'values-night');
mkdirSync(valuesNight, { recursive: true });
const colors = (bg) => `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="clubs_background">${bg}</color>\n</resources>\n`;
writeFileSync(join(values, 'clubs_colors.xml'), colors('#FFFFFF'));
writeFileSync(join(valuesNight, 'clubs_colors.xml'), colors('#111412'));
const stylesPath = join(values, 'styles.xml');
if (existsSync(stylesPath)) {
  let styles = readFileSync(stylesPath, 'utf8');
  // splash-тема: фон из цвета, а не из белой картинки; окно приложения — тот же цвет
  styles = styles.replace(/<item name="android:background">@drawable\/splash<\/item>/, '<item name="android:background">@color/clubs_background</item>');
  if (!styles.includes('android:windowBackground')) styles = styles.replace(/(<style name="AppTheme\.NoActionBar"[^>]*>)/, '$1\n        <item name="android:windowBackground">@color/clubs_background</item>');
  // Android 12+ SplashScreen API: фон темы (светлая/тёмная), адаптивная иконка на фирменном круге, после — основная тема.
  // Веб-экран загрузки (shim/app-splash.*) повторяет ровно эту картинку, поэтому передача без второго сплэша и вспышки.
  styles = styles.replace(/<style name="AppTheme\.NoActionBarLaunch"[\s\S]*?<\/style>/, `<style name="AppTheme.NoActionBarLaunch" parent="Theme.SplashScreen">
        <item name="windowSplashScreenBackground">@color/clubs_background</item>
        <item name="windowSplashScreenAnimatedIcon">@drawable/itc_splash_icon</item>
        <item name="windowSplashScreenIconBackgroundColor">@color/ic_launcher_background</item>
        <item name="postSplashScreenTheme">@style/AppTheme.NoActionBar</item>
        <item name="android:background">@color/clubs_background</item>
    </style>`);
  writeFileSync(stylesPath, styles);
}
console.log('[patch-android] цвета светлой/тёмной темы + SplashScreen API OK');

// ---- демо-сборка (APP_DEMO=1): своё имя/ID (ставится рядом с обычным приложением) + иконки бренда, если есть
import { readdirSync, cpSync } from 'node:fs';
const DEMO = /^(1|true|yes)$/i.test(process.env.APP_DEMO || '');
const APP_NAME = process.env.APP_NAME || (DEMO ? 'ИТС Кружки' : 'Кружки КИПФИН');
const stringsPath = join(app, 'res', 'values', 'strings.xml');
if (existsSync(stringsPath)) {
  let s = readFileSync(stringsPath, 'utf8');
  s = s.replace(/(<string name="app_name">)[^<]*(<\/string>)/, `$1${APP_NAME}$2`).replace(/(<string name="title_activity_main">)[^<]*(<\/string>)/, `$1${APP_NAME}$2`);
  writeFileSync(stringsPath, s);
}
const gradlePath = join(root, 'android', 'app', 'build.gradle');
if (existsSync(gradlePath)) {
  let g = readFileSync(gradlePath, 'utf8').replace(/\n\s*applicationIdSuffix "\.demo"/, '');
  if (DEMO) g = g.replace(/(applicationId "[^"]+")/, '$1\n        applicationIdSuffix ".demo"');
  writeFileSync(gradlePath, g);
}
const brand = process.env.BRAND_ANDROID_DIR || resolve(root, '../../brand/android');
let icons = 0;
if (DEMO && existsSync(brand)) {
  const walk = (dir) => { for (const n of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, n.name);
    if (n.isDirectory()) { if (/^(mipmap|drawable|values)[\w-]*$/.test(n.name) && readdirSync(p).some(f => /^ic_launcher/.test(f))) { mkdirSync(join(app, 'res', n.name), { recursive: true });
      for (const f of readdirSync(p)) if (/^ic_launcher/.test(f)) { cpSync(join(p, f), join(app, 'res', n.name, f)); icons++; } } else walk(p); }
  } };
  walk(brand);
}
console.log(`[patch-android] имя «${APP_NAME}»${DEMO ? ', applicationId +.demo' : ''}; иконок бренда: ${icons}${DEMO && !existsSync(brand) ? ' (нет ' + brand + ')' : ''}`);

// ---- версия приложения: android/version.json (build-apk.mjs поднимает её перед каждой сборкой)
{
  const ver = readVersion('android'); // v<номер из ../version.json><suffix>
  if (existsSync(gradlePath)) {
    const g = readFileSync(gradlePath, 'utf8')
      .replace(/versionCode\s+\d+/, `versionCode ${ver.versionCode}`)
      .replace(/versionName\s+"[^"]*"/, `versionName "${ver.versionName}"`);
    writeFileSync(gradlePath, g);
  }
  console.log(`версия: ${ver.versionName} (code ${ver.versionCode})`);
}

// ---- подпись release из окружения (ключ и пароли не хранятся в репозитории); без ANDROID_KEYSTORE release не подписывается
// ---- экран сканера QR (CameraX + ML Kit)
{
  let m = readFileSync(manifestPath, 'utf8');
  if (!m.includes('ru.kipfin.clubs.ScanActivity')) {
    m = m.replace(/(\s*<\/application>)/, `
        <activity android:name="ru.kipfin.clubs.ScanActivity" android:exported="false" android:screenOrientation="portrait" android:theme="@style/Theme.AppCompat.NoActionBar" />$1`);
    writeFileSync(manifestPath, m);
  }
}
if (existsSync(gradlePath)) {
  let g = readFileSync(gradlePath, 'utf8');
  if (!g.includes('clubsRelease')) {
    g = g.replace(/\n(\s*)buildTypes\s*\{/, `
    signingConfigs {
        clubsRelease {
            if (System.getenv('ANDROID_KEYSTORE')) {
                storeFile file(System.getenv('ANDROID_KEYSTORE'))
                storePassword System.getenv('ANDROID_KEYSTORE_PASSWORD')
                keyAlias System.getenv('ANDROID_KEY_ALIAS')
                keyPassword System.getenv('ANDROID_KEY_PASSWORD') ?: System.getenv('ANDROID_KEYSTORE_PASSWORD')
            }
        }
    }
$1buildTypes {`);
    g = g.replace(/(\n\s*release\s*\{)/, `$1\n            if (System.getenv('ANDROID_KEYSTORE')) signingConfig signingConfigs.clubsRelease`);
    writeFileSync(gradlePath, g);
  }
}

// ---- нативные функции (phase 2 C): «Мои кружки», напоминания, уведомления об изменениях, виджеты, ярлыки.
// Исходники — android/native/ (java, res, test); здесь копируются в сгенерированный проект и подключаются в манифест/gradle.
// Только AndroidX + платформа: без Google Play Services (работает на Huawei/AppGallery и прошивках без GMS).
{
  const nativeDir = join(root, 'native');
  const appDir = join(root, 'android', 'app');
  const appId = JSON.parse(readFileSync(join(root, 'capacitor.config.json'), 'utf8')).appId + (DEMO ? '.demo' : '');
  cpSync(join(nativeDir, 'java'), join(appDir, 'src', 'main', 'java'), { recursive: true });
  cpSync(join(nativeDir, 'res'), join(appDir, 'src', 'main', 'res'), { recursive: true });
  cpSync(join(nativeDir, 'test'), join(appDir, 'src', 'test', 'java'), { recursive: true });
  const sc = join(appDir, 'src', 'main', 'res', 'xml', 'itc_shortcuts.xml');
  writeFileSync(sc, readFileSync(sc, 'utf8').replaceAll('PACKAGE_NAME', appId));

  let m = readFileSync(manifestPath, 'utf8');
  if (!m.includes('ru.kipfin.clubs.NextClassWidget')) {
    m = m.replace(/(<category android:name="android.intent.category.LAUNCHER" \/>\s*<\/intent-filter>)/, `$1

            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="itckruzhki" android:host="open" />
            </intent-filter>
            <meta-data android:name="android.app.shortcuts" android:resource="@xml/itc_shortcuts" />`);
    m = m.replace(/(\s*<\/application>)/, `
        <receiver android:name="ru.kipfin.clubs.NextClassWidget" android:exported="false" android:label="@string/widget_next_name">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
                <action android:name="ru.kipfin.clubs.WIDGET_TICK" />
            </intent-filter>
            <meta-data android:name="android.appwidget.provider" android:resource="@xml/widget_next_info" />
        </receiver>
        <receiver android:name="ru.kipfin.clubs.TodayWidget" android:exported="false" android:label="@string/widget_today_name">
            <intent-filter><action android:name="android.appwidget.action.APPWIDGET_UPDATE" /></intent-filter>
            <meta-data android:name="android.appwidget.provider" android:resource="@xml/widget_today_info" />
        </receiver>
        <service android:name="ru.kipfin.clubs.TodayWidgetService" android:exported="false" android:permission="android.permission.BIND_REMOTEVIEWS" />
        <receiver android:name="ru.kipfin.clubs.ReminderReceiver" android:exported="false">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
                <action android:name="android.intent.action.TIME_SET" />
                <action android:name="android.intent.action.TIMEZONE_CHANGED" />
            </intent-filter>
        </receiver>$1`);
    m = m.replace(/(\s*<\/manifest>)/, `
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />$1`);
    writeFileSync(manifestPath, m);
  }
  let g = readFileSync(gradlePath, 'utf8');
  if (!g.includes('com.google.mlkit:barcode-scanning')) { // сканер QR: CameraX + ML Kit (модель внутри APK, без Play-сервисов)
    g = g.replace(/(\ndependencies\s*\{)/, `$1
    implementation "com.google.mlkit:barcode-scanning:17.3.0"
    implementation "androidx.camera:camera-camera2:1.4.2"
    implementation "androidx.camera:camera-lifecycle:1.4.2"
    implementation "androidx.camera:camera-view:1.4.2"`);
    writeFileSync(gradlePath, g);
  }
  if (!g.includes('androidx.work:work-runtime')) {
    g = g.replace(/(\ndependencies\s*\{)/, `$1
    implementation "androidx.work:work-runtime:2.10.5"
    testImplementation "org.json:json:20250517"`);
    writeFileSync(gradlePath, g);
  }
  console.log(`[patch-android] нативные функции: виджеты, напоминания, ярлыки (${appId})`);
}
