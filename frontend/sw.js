/* Service worker: офлайн-оболочка + Web Push.
   Строки с маркерами `// __BUILD_ID__` и `// __PRECACHE__` переписывает сборка (`server.py build web|ios`): версия кэша и полный список файлов.
   Без сборки (режим serve) работают значения по умолчанию ниже — файл остаётся валидным JS. */
'use strict';
const BUILD_ID = 'dev'; // __BUILD_ID__
const CACHE = `clubs-shell-${BUILD_ID}`;
const API_CACHE = `clubs-api-${BUILD_ID}`;
const PRECACHE = ['/', '/clubs.html', '/offline.html', '/css/tokens.css', '/css/campus.css', '/css/components.css', '/css/platform.css', '/js/theme-init.js']; // __PRECACHE__
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // addAll атомарен: один недоступный файл ломает всё, поэтому добавляем по одному и не падаем.
    await Promise.all(PRECACHE.map(url => cache.add(new Request(url, { cache: 'reload' })).catch(() => null)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (/^clubs-(shell|api)-/.test(key) && ![CACHE, API_CACHE].includes(key)) await caches.delete(key);
    await self.clients.claim();
  })());
});

const PUBLIC_API = /^\/api\/(schedule|clubs|categories|leaders|rooms)(\/|$|\?)/;
const API_MAX_AGE = 48 * 3600 * 1000;
const API_MAX_ENTRIES = 100;
async function rememberApi(cache, request, response) {
  const headers = new Headers(response.headers);
  headers.set('X-Clubs-Cached-At', new Date().toISOString());
  await cache.put(request, new Response(await response.clone().arrayBuffer(), { status: response.status, headers }));
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - API_MAX_ENTRIES))) await cache.delete(key);
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/admin') || url.pathname.startsWith('/api/push') || url.pathname === '/sw.js') return; // никогда не кэшируем

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        if (fresh.ok && !url.pathname.startsWith('/admin')) await (await caches.open(CACHE)).put(request, fresh.clone());
        return fresh;
      } catch {
        return (await caches.match(request, { ignoreSearch: true })) || (await caches.match(OFFLINE_URL)) || Response.error();
      }
    })());
    return;
  }
  if (PUBLIC_API.test(url.pathname + url.search)) {
    // сеть в приоритете, при её отсутствии — последняя удачная копия (расписание офлайн)
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        if (fresh.ok) await rememberApi(await caches.open(API_CACHE), request, fresh);
        return fresh;
      } catch {
        const cache = await caches.open(API_CACHE);
        const cached = await cache.match(request);
        const savedAt = cached && Date.parse(cached.headers.get('X-Clubs-Cached-At'));
        if (cached && Number.isFinite(savedAt) && Date.now() - savedAt <= API_MAX_AGE) {
          const headers = new Headers(cached.headers);
          headers.set('X-Clubs-Offline', '1');
          return new Response(await cached.arrayBuffer(), { status: cached.status, headers });
        }
        if (cached) await cache.delete(request);
        throw new Error('offline');
      }
    })());
    return;
  }
  if (url.pathname.startsWith('/api/')) return;
  if (/\.(css|js|woff2|png|svg|webmanifest|json)$/.test(url.pathname)) {
    // Always try current assets first; stale JS must not hide a saved fix in dev.
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch { return (await cache.match(request)) || Response.error(); }
    })());
  }
});

/* ---------- Web Push ---------- */
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  const title = String(data.title || 'KipClub');
  const options = {
    body: String(data.body || ''),
    icon: '/icons/icon-192.png?v=kc3',
    badge: '/icons/badge-96.png?v=kc3',
    tag: data.tag ? String(data.tag) : undefined,
    lang: 'ru',
    data: { url: typeof data.url === 'string' ? data.url : '/' },
  };
  // userVisibleOnly: на каждый push обязательно показываем уведомление (иначе Safari/Chrome отзовут подписку)
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  let target = new URL('/', self.location.origin);
  try { const u = new URL(event.notification.data?.url || '/', self.location.origin); if (u.origin === self.location.origin) target = u; } catch { /* оставляем / */ }
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
        await client.focus();
        if ('navigate' in client) { try { await client.navigate(target.href); } catch { /* ignore */ } }
        return;
      }
    }
    await self.clients.openWindow(target.href);
  })());
});

/* Подписку отозвал браузер (смена ключей / срок): тихо пересоздаём на те же кружки, если сервер даёт ключ. */
self.addEventListener('pushsubscriptionchange', event => {
  event.waitUntil((async () => {
    try {
      const { publicKey } = await (await fetch('/api/push/vapid-public-key')).json();
      const pad = '='.repeat((4 - (publicKey.length % 4)) % 4);
      const raw = atob((publicKey + pad).replace(/-/g, '+').replace(/_/g, '/'));
      const key = Uint8Array.from(raw, c => c.charCodeAt(0));
      const sub = await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      const json = sub.toJSON();
      // Какие кружки были — неизвестно (старая подписка уже недействительна): подписываем «на все».
      await fetch('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys, club_id: null }) });
    } catch { /* повторно предложим подписаться на странице кружка */ }
  })());
});
