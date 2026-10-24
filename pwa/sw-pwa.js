/* Дополнение service worker для сборки pwa (importScripts из sw.js): значок на иконке приложения (Badging API).
 * Счётчик непросмотренных изменений «Моих кружков» хранится в Cache Storage: страница пишет его, push прибавляет 1. */
'use strict';
const ITC_BADGE_CACHE = 'itc-badge';
const ITC_BADGE_KEY = '/__itc/badge';
async function itcBadgeGet() {
  try { const r = await (await caches.open(ITC_BADGE_CACHE)).match(ITC_BADGE_KEY); return r ? (parseInt(await r.text(), 10) || 0) : 0; } catch { return 0; }
}
async function itcBadgeSet(n) {
  try { await (await caches.open(ITC_BADGE_CACHE)).put(ITC_BADGE_KEY, new Response(String(n))); } catch { /* ignore */ }
  try {
    if (n > 0 && self.navigator.setAppBadge) await self.navigator.setAppBadge(n);
    else if (self.navigator.clearAppBadge) await self.navigator.clearAppBadge();
  } catch { /* Badging API нет (iOS < 16.4, часть Android-лаунчеров) */ }
}
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { /* текстовый push — тоже изменение */ }
  if (data && data.badge === false) return;
  event.waitUntil(itcBadgeGet().then(n => itcBadgeSet(n + 1)));
});
self.addEventListener('message', event => {
  const d = event.data || {};
  if (d.type === 'itc-badge' && Number.isInteger(d.count) && d.count >= 0) event.waitUntil(itcBadgeSet(d.count));
});
