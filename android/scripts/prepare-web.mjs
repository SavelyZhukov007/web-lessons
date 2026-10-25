import { readVersion } from './version.mjs';
// Делает www/ = копия frontend/ сайта + shim (настройка адреса сервера). Исходный frontend НЕ меняется.
import { cpSync, rmSync, mkdirSync, readdirSync, readFileSync, writeFileSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

function findFrontend() {
  const candidates = [process.env.FRONTEND_DIR, resolve(root, '../frontend'), resolve(root, '../proj/frontend')].filter(Boolean);
  for (const c of candidates) if (existsSync(join(c, 'index.html'))) return resolve(c);
  throw new Error('Не найден frontend/ (искал: ' + candidates.join(', ') + '). Задай FRONTEND_DIR=путь.');
}

const src = findFrontend();
const out = process.env.WWW_OUT ? resolve(process.env.WWW_OUT) : join(root, 'www');
rmSync(out, { recursive: true, force: true });
cpSync(src, out, { recursive: true, filter: p => !/[\\/](tests)([\\/]|$)/.test(relative(src, p)) });
// В APK нет ни service worker, ни manifest, ни страницы установки PWA (приложение уже «установлено»; SW с кэшем мешал бы обновлениям)
for (const f of ['sw.js', 'manifest.webmanifest', 'install.html', 'offline.html', 'build-info.json']) rmSync(join(out, f), { force: true });
// Страницы распространения (/ios, /android/) и плашка установки нужны только сайту, не APK.
for (const f of ['ios', 'android', 'js/install-banner.js', 'js/distribution.js', 'css/distribution.css']) rmSync(join(out, f), { recursive: true, force: true });
for (const f of readdirSync(out).filter((n) => n.endsWith('.html'))) {
  const p = join(out, f); const html = readFileSync(p, 'utf8');
  const stripped = html.replace(/\n?\s*<script type="module" src="\/js\/install-banner\.js"><\/script>/, '');
  if (stripped !== html) writeFileSync(p, stripped);
}
// shim + экран настроек
mkdirSync(join(out, 'js'), { recursive: true });
// APP_DEMO=1 — демо/офлайн-сборка: вместо shim сервера подключается локальный бэкенд (localStorage), сеть не нужна
const DEMO = /^(1|true|yes)$/i.test(process.env.APP_DEMO || '');
// Публичный канал (p, не демо): адрес сервера зашит при сборке (APP_SERVER_URL, по умолчанию production),
// экрана «Сервер расписания» и смены сервера нет. Каналы l/i — как раньше (адрес вводит пользователь).
const FIXED_SERVER = !DEMO && (process.env.ITC_CHANNEL || readVersion('android').channel) === 'p';
const PROD_SERVER = 'http://lekora.ru:7443';
if (DEMO) {
  // демо + инструменты подключения к тестовому серверу (app-shim), Excel-выгрузка без сервера (xlsx-lite)
  for (const f of ['demo-backend.js', 'app-shim.js', 'xlsx-lite.js']) cpSync(join(root, 'shim', f), join(out, 'js', f));
} else {
  cpSync(join(root, 'shim', 'app-shim.js'), join(out, 'js', 'app-shim.js'));
  if (!FIXED_SERVER) { // экран выбора сервера — только l/i
    cpSync(join(root, 'shim', 'server-setup.js'), join(out, 'js', 'server-setup.js'));
    cpSync(join(root, 'shim', 'settings.html'), join(out, 'settings.html'));
  }
}
cpSync(join(root, 'shim', 'app-shell.css'), join(out, 'css', 'app-shell.css'));
// нативная оболочка (только APK): html.is-native, safe area, «Назад», календарь, выход/вход, бренд — см. shim/native-shell.*
cpSync(join(root, 'shim', 'native-shell.js'), join(out, 'js', 'native-shell.js'));
cpSync(join(root, 'shim', 'native-shell.css'), join(out, 'css', 'native-shell.css'));
// нативные функции (phase 2 C): «Мои кружки», напоминания, виджеты, ярлыки, офлайн-кэш, QR-посещаемость — см. shim/native-features.*
for (const f of ['native-features.js', 'native-motion.js', 'qr-checkin.js']) cpSync(join(root, 'shim', f), join(out, 'js', f));
for (const f of ['native-features.css', 'native-motion.css']) cpSync(join(root, 'shim', f), join(out, 'css', f));
cpSync(join(root, 'shim', 'qr.html'), join(out, 'qr.html'));
cpSync(join(root, 'node_modules', 'jsqr', 'dist', 'jsQR.js'), join(out, 'js', 'jsQR.js'));
// phase 2 F: экран загрузки, новое «Расписание» (вместо js/schedule.js сайта), обновления внутри приложения, админка
const ver = readVersion('android'); // номер — общий ../version.json (APK и PWA)
// адрес проверки обновлений: APP_UPDATE_URL=https://<сайт>/api/app/android при сборке (или itc.updateUrl в приложении);
// без него обычная сборка берёт адрес сервера из настроек, демо — молча не проверяет
const UPDATE_URL = (process.env.APP_UPDATE_URL || '').trim();
writeFileSync(join(out, 'js', 'app-splash.js'), readFileSync(join(root, 'shim', 'app-splash.js'), 'utf8').replace('%%VERSION%%', ver.versionName));
writeFileSync(join(out, 'js', 'app-update.js'), readFileSync(join(root, 'shim', 'app-update.js'), 'utf8').replace("'%%UPDATE_URL%%'", JSON.stringify(UPDATE_URL)));
for (const f of ['app-schedule.js', 'app-admin.js', 'app-student.js', 'app-extras.js']) cpSync(join(root, 'shim', f), join(out, 'js', f));
for (const f of ['app-schedule.css', 'app-splash.css', 'app-student.css']) cpSync(join(root, 'shim', f), join(out, 'css', f));
{ // передний слой адаптивной иконки (как у системного сплэша); нет бренда — maskable-иконка сайта
  const fg = [process.env.BRAND_ANDROID_DIR && join(process.env.BRAND_ANDROID_DIR, 'res', 'mipmap-xxxhdpi', 'ic_launcher_foreground.png'),
    resolve(root, '../assets/brand/kipclub/android/res/mipmap-xxxhdpi/ic_launcher_foreground.png'),
    join(root, 'android', 'app', 'src', 'main', 'res', 'mipmap-xxxhdpi', 'ic_launcher_foreground.png')].filter(Boolean).find(existsSync);
  mkdirSync(join(out, 'icons'), { recursive: true });
  cpSync(fg || join(out, 'icons', 'maskable-512.png'), join(out, 'icons', 'splash-fg.png'));
}
const SPLASH_HTML = '<div id="itc-splash" role="progressbar" aria-label="Загрузка приложения" aria-valuemin="0" aria-valuemax="100">' +
  '<div class="itc-splash-icon"><img src="/icons/splash-fg.png" alt="" width="240" height="240" decoding="sync"></div>' +
  '<div class="itc-splash-mid"><p class="itc-splash-phrase" aria-live="off">Открываем приложение…</p><div class="itc-splash-bar"><i></i></div></div>' +
  '<p class="itc-splash-foot"><span class="itc-splash-version">Версия ' + ver.versionName + '</span><b>Продукт ИТС КИПФИН</b></p></div>';
const NATIVE = '<script>window.ITC_CHANNEL=' + JSON.stringify(ver.channel) + ';window.ITC_VERSION=' + JSON.stringify(ver.versionName) + '</script>' +
  '<script src="/js/app-splash.js"></script><link rel="stylesheet" href="/css/app-splash.css">' +
  '<script src="/js/native-shell.js"></script><script src="/js/native-features.js"></script><script src="/js/native-motion.js"></script>' +
  '<link rel="stylesheet" href="/css/app-student.css"><script src="/js/app-student.js"></script><script src="/js/app-extras.js" defer></script>' +
  '<script src="/js/app-update.js" defer></script><script src="/js/app-admin.js" defer></script>'; // t100 perf: некритичные — defer
const SCHEDULE_HEAD = '<link rel="preload" href="/fonts/GolosText-Variable.woff2" as="font" type="font/woff2" crossorigin>' +
  '<link rel="modulepreload" href="/js/app-schedule.js"><link rel="modulepreload" href="/js/api.js"><link rel="modulepreload" href="/js/schedule-dates.js"><link rel="modulepreload" href="/js/icons.js">' +
  '<link rel="stylesheet" href="/css/app-schedule.css">';

// опционально: предзаданный адрес сервера (APP_DEFAULT_SERVER=http://IP:PORT) — тогда экран настроек при первом запуске не нужен
const defServer = DEMO ? '' : ((FIXED_SERVER ? (process.env.APP_SERVER_URL || process.env.APP_DEFAULT_SERVER || PROD_SERVER) : process.env.APP_DEFAULT_SERVER) || '').trim().replace(/\/+$/, '');
const PRE = defServer ? '<script src="/js/default-server.js"></script>\n    ' : '';
if (defServer) writeFileSync(join(out, 'js', 'default-server.js'), `window.APP_DEFAULT_SERVER=${JSON.stringify(defServer)};${FIXED_SERVER ? 'window.APP_FIXED_SERVER=true;' : ''}\n`);
if (FIXED_SERVER) console.log(`[prepare-web] канал p: сервер зашит ${defServer}, экран выбора сервера отключён`);

// вставляем shim первым скриптом в <head> каждой html-страницы (до модулей и api.js)
const SHIM = DEMO ? 'demo-backend.js' : 'app-shim.js';
const TAG = DEMO ? '<script>window.ITC_CHANNEL=' + JSON.stringify(ver.channel) + '</script><script src="/js/xlsx-lite.js"></script><script src="/js/demo-backend.js"></script><script src="/js/app-shim.js"></script>' : PRE + '<script src="/js/app-shim.js"></script>';
let patched = 0;
const stripPwa = html => html
  .replace(/\s*<link rel="manifest"[^>]*>/g, '')
  .replace(/\s*<script type="module" src="\/js\/pwa-register\.js"><\/script>/g, '');
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { walk(p); continue; }
    if (!name.endsWith('.html')) continue;
    let html = stripPwa(readFileSync(p, 'utf8'));
    if (html.includes('native-shell.js')) continue;
    const tags = name === 'settings.html' ? NATIVE : (html.includes(SHIM) ? NATIVE : `${TAG}\n    ${NATIVE}`);
    let next = html.replace(/<head[^>]*>/i, m => `${m}\n    ${tags}`);
    if (name !== 'settings.html') next = next.replace(/<body[^>]*>/i, m => `${m}\n    ${SPLASH_HTML}`);
    if (name === 'index.html' && dir === out) {
      next = next.replace('<script type="module" src="/js/schedule.js"></script>', '<script type="module" src="/js/app-schedule.js"></script>')
        .replace('</head>', `    ${SCHEDULE_HEAD}\n</head>`);
    }
    if (next === html) { console.warn('нет <head> в', p); continue; }
    writeFileSync(p, next); patched++;
  }
})(out);
console.log(`[prepare-web]${DEMO ? ' DEMO' : ''} ${src} -> ${out}; html с shim: ${patched}`);
