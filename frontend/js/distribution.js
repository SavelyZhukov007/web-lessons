// Логика страниц /ios, /ios/pwa, /android/ (CSP: script-src 'self' — только внешний файл).
import { parseIosVersion, isTooOld, tooOldMessage } from './ios-version.js?v=kc5';

const ua = navigator.userAgent || '';
export const isIOS = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
export const isAndroid = /Android/i.test(ua);
export const isStandalone = () => navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
// На iOS все браузеры — WebKit, но «На экран Домой» с иконкой PWA надёжно доступен только в Safari.
const OTHER_IOS = [
    [/CriOS/, 'Chrome'], [/FxiOS/, 'Firefox'], [/EdgiOS/, 'Edge'], [/OPiOS|OPT\//, 'Opera'], [/YaBrowser|YaApp/, 'Яндекс'],
    [/GSA\//, 'Google'], [/Telegram/i, 'Telegram'], [/VKClient|vkclient/i, 'VK'], [/Instagram/, 'Instagram'], [/FBAN|FBAV/, 'Facebook'],
];
export function iosBrowser() {
    for (const [re, name] of OTHER_IOS) if (re.test(ua)) return name;
    if (!/Safari\//.test(ua)) return 'встроенный браузер'; // WKWebView приложений-мессенджеров
    return null; // Safari
}
const $ = (id) => document.getElementById(id);

function formatSize(bytes) {
    return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace('.', ',')} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`;
}

async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* fallback ниже */ }
    const field = $('dist-link');
    field.focus(); field.select(); field.setSelectionRange(0, text.length);
    try { return document.execCommand('copy'); } catch { return false; }
}

function initIos() {
    if (isStandalone()) { $('ios-installed').hidden = false; return; }
    const ver = isIOS ? parseIosVersion(ua) : null;
    if (isTooOld(ver)) { // старая iOS: шаги установки бесполезны — объясняем, как обновиться
        $('ios-too-old-text').textContent = tooOldMessage(ver);
        $('ios-too-old').hidden = false;
        $('ios-steps').hidden = true;
        $('ios-min-note').hidden = true;
        return;
    }
    const browser = isIOS ? iosBrowser() : null;
    if (!browser) return;
    const url = `${location.origin}/ios/pwa`;
    $('ios-open-in-safari').hidden = false;
    $('ios-browser-note').textContent = `Сейчас страница открыта в браузере «${browser}». Установить приложение на iPhone можно только из Safari: скопируйте ссылку и вставьте её в адресную строку Safari.`;
    $('dist-link').value = url;
    $('dist-copy-btn').addEventListener('click', async () => {
        const ok = await copyText(url);
        $('dist-copy-status').textContent = ok ? 'Ссылка скопирована. Откройте Safari и вставьте её в адресную строку.' : 'Не удалось скопировать — выделите ссылку и скопируйте вручную.';
    });
}

function initIosPwa() {
    if (isStandalone()) { location.replace('/?source=pwa'); return; }
    $('pwa-redirect').hidden = true;
    const overlay = $('pwa-overlay');
    overlay.hidden = false;
    overlay.querySelector('a')?.focus({ preventScroll: true });
}

// Сервер выбирает опубликованный APK; GitHub /latest не учитывает бета-релизы.
export const APK_URL = '/android/download';

async function initAndroid() {
    const btn = $('apk-download'), meta = $('apk-meta');
    btn.href = APK_URL;
    let info;
    try {
        const res = await fetch('/api/app/android', { headers: { Accept: 'application/json' }, cache: 'no-store' });
        if (!res.ok) throw new Error(String(res.status));
        info = await res.json();
    } catch {
        meta.textContent = 'Не удалось проверить версию — попробуйте скачать файл.';
        return;
    }
    if (info.rustore_url) { $('rustore-link').href = info.rustore_url; $('rustore-block').hidden = false; }
    if (!info.available) { meta.hidden = true; return; }
    // Только безопасный URL из контракта; при ошибке метаданных остаётся рабочий /android/download.
    const downloadUrl = String(info.download_url || info.url || '');
    if (downloadUrl.startsWith('/') && !downloadUrl.startsWith('//') || downloadUrl.startsWith('https://')) btn.href = downloadUrl;
    const parts = [info.version ? `Версия ${info.version}` : null, formatSize(info.size), info.updated ? new Date(info.updated).toLocaleDateString('ru-RU') : null];
    meta.textContent = parts.filter(Boolean).join(' · ');
    if (info.sha256) { const sha = $('apk-sha'); sha.textContent = `SHA-256: ${info.sha256}`; sha.hidden = false; }
}

const page = document.body.dataset.distPage;
if (page === 'ios') initIos();
else if (page === 'ios-pwa') initIosPwa();
else if (page === 'android') initAndroid();
