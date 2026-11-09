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
    const queue = [...PRECACHE];
    await Promise.all(Array.from({ length: 4 }, async () => {
      while (queue.length) { const url = queue.shift(); try { await cache.add(new Request(url, { cache: 'reload' })); } catch { /* optional asset, retry on demand */ } }
    }));
    if (!self.registration?.active) await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    // One previous shell remains usable by an already open page and its lazy imports.
    for (const prefix of ['clubs-shell-', 'clubs-api-']) {
      const versions = keys.filter(key => key.startsWith(prefix));
      for (const key of versions.slice(0, -2)) if (![CACHE, API_CACHE].includes(key)) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

const PUBLIC_API = /^\/api\/(schedule|clubs|categories|leaders|rooms)(\/|$|\?)/;
// Страница разрешает активацию новой версии после сохранения формы.
self.addEventListener('message', event => {
  if (event.data?.type === 'clubs:activate') event.waitUntil(self.skipWaiting());
});
const API_MAX_AGE = 48 * 3600 * 1000;
const API_MAX_ENTRIES = 100;
async function rememberApi(cache, request, response) {
  const headers = new Headers(response.headers);
  headers.set('X-Clubs-Cached-At', new Date().toISOString());
  await cache.put(request, new Response(await response.clone().arrayBuffer(), { status: response.status, headers }));
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - API_MAX_ENTRIES))) await cache.delete(key);
}

const PUSH_PREFS_CACHE = 'clubs-push-preferences';
const PUSH_PREFS_KEY = '/__clubs/push-preferences';
async function savePushPreferences(endpoint, status, scheduleSettings) {
  const cache = await caches.open(PUSH_PREFS_CACHE);
  const key = new Request(new URL(PUSH_PREFS_KEY, self.location.origin));
  let settings=scheduleSettings;
  try {
    if (!settings) {
      const saved=await cache.match(key), previous=saved?await saved.json():null;
      if(previous?.endpoint===endpoint)settings=previous.schedule_settings;
      const response=await fetch('/api/push/schedule-settings/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint})});
      if(response.ok)settings=await response.json();
    }
  }catch{/* Keep the last explicit opt-in if the settings endpoint is temporarily offline. */}
  await cache.put(key, Response.json({ endpoint, ...status, schedule_settings:settings }));
}
async function pushStatus(endpoint) {
  const response = await fetch('/api/push/status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint }) });
  if (!response.ok) throw new Error('push status unavailable');
  return response.json();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.method === 'POST' && /^\/api\/push\/(subscribe|unsubscribe|preferences|status|sync|schedule-settings(?:\/read)?)$/.test(url.pathname)) {
    event.respondWith((async () => {
      const copy = request.clone();
      const response = await fetch(request);
      if (response.ok) {
        try {
          const { endpoint } = await copy.json();
          // Успешная операция могла сузить согласие. Старая копия больше не основание для восстановления.
          if (!url.pathname.endsWith('/status')) await (await caches.open(PUSH_PREFS_CACHE)).delete(new Request(new URL(PUSH_PREFS_KEY, self.location.origin)));
          if (endpoint) {
            const scheduleSettings=url.pathname.includes('/schedule-settings')?await response.clone().json():undefined;
            const status = /\/(status|sync)$/.test(url.pathname) ? await response.clone().json() : await pushStatus(endpoint);
            await savePushPreferences(endpoint, status, scheduleSettings);
          }
        } catch { /* API-операция выполнена; отсутствие копии не расширяет подписку при восстановлении. */ }
      }
      return response;
    })());
    return;
  }
  if (request.method !== 'GET') return;
  if (['/build-info.json', '/version.json'].includes(url.pathname)) return;
  if (url.pathname.startsWith('/api/admin') || url.pathname.startsWith('/api/push') || url.pathname === '/sw.js') return; // никогда не кэшируем

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(new Request(request, { cache: 'reload' }));
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
        const names = caches.keys ? (await caches.keys()).filter(key => key.startsWith('clubs-api-')).reverse() : [];
        for (const name of [API_CACHE, ...names.filter(name => name !== API_CACHE)]) {
          const store = name === API_CACHE ? cache : await caches.open(name);
          const cached = await store.match(request);
          const savedAt = cached && Date.parse(cached.headers.get('X-Clubs-Cached-At'));
          if (cached && Number.isFinite(savedAt) && Date.now() - savedAt <= API_MAX_AGE) {
            const headers = new Headers(cached.headers); headers.set('X-Clubs-Offline', '1');
            return new Response(await cached.arrayBuffer(), { status: cached.status, headers });
          }
          if (cached) await store.delete(request);
        }
        throw new Error('offline');
      }
    })());
    return;
  }
  if (url.pathname.startsWith('/api/')) return;
  if (/^\/assets\/[a-f0-9]{20}\//.test(url.pathname)) {
    event.respondWith((async () => {
      // Hashed same-origin assets have exactly one public representation. Module/font
      // requests carry Origin while precache requests do not (Vary: Origin).
      const cached = await caches.match(request, { ignoreVary: true, ignoreSearch: true });
      if (cached) return cached; // immutable graph, including a still-open previous shell
      const response = await fetch(request);
      if (response.ok) event.waitUntil?.((await caches.open(CACHE)).put(request, response.clone()));
      return response;
    })());
    return;
  }
  if (/\.(css|js|woff2|png|svg|webmanifest|json)$/.test(url.pathname)) {
    // Always try current assets first; stale JS must not hide a saved fix in dev.
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const response = await fetch(new Request(request, { cache: 'reload' }));
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        const cached = await cache.match(request);
        if (cached) return cached;
        // First offline navigation may ask for an asset with a version query
        // or different browser-supplied Vary headers than precaching did.
        if (PRECACHE.includes(url.pathname)) {
          const bundled = await cache.match(url.pathname, { ignoreVary: true });
          if (bundled) return bundled;
        }
        return Response.error();
      }
    })());
  }
});

/* ---------- Web Push ---------- */
let pushQueue=Promise.resolve(), receiptInstallPromise;
async function receipt(id, kind) {
  if (!Number.isSafeInteger(id) || id <= 0) return;
  try {
    const install=await(receiptInstallPromise ||= (async()=>{
      const cache=await caches.open('clubs-notification-receipts');
      const key=new Request(new URL('/__clubs/receipt-install',self.location.origin));
      const previous=await cache.match(key);
      const id=previous?await previous.text():crypto.randomUUID().replaceAll('-','');
      if(!previous)await cache.put(key,new Response(id));
      return id;
    })());
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),4000);
    try{await fetch('/api/announcements/'+id+'/receipt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({install_id:install,channel:'web',kind}),signal:controller.signal});}
    finally{clearTimeout(timer);}
  }catch{/* Best effort only: lack of receipts is not proof a notification was not seen. */}
}
async function groupedPush(data) {
  const kind=['cancelled','moved','cancel','reschedule'].includes(data.kind)?'changes':data.kind==='reminder'?'reminders':data.kind==='digest'?'digest':'announcements';
  const group=kind+':'+(Number.isInteger(data.club_id)?data.club_id:'general');
  const options={body:String(data.body||''),icon:'/icons/icon-192.png?v=kc4',badge:'/icons/badge-96.png?v=kc4',tag:'kc:'+group,renotify:false,lang:'ru',data:{url:typeof data.url==='string'?data.url:'/',broadcast_id:data.broadcast_id}};
  let title=String(data.title||'KipClub');
  try {
    const cache=await caches.open('clubs-notification-groups');
    const key=new Request(new URL('/__clubs/notification-group/'+encodeURIComponent(group),self.location.origin));
    const response=await cache.match(key);let row=response?await response.json():null;
    const day=new Date(Date.now()+10800000).toISOString().slice(0,10);
    if(!row || row.day!==day)row={seen:[],items:[],count:0,time:Date.now(),day};
    const id=String(data.tag||data.title+'|'+data.body);
    if(!row.seen.includes(id)){row.seen.push(id);row.seen=row.seen.slice(-100);row.count=Math.min(100,row.count+1);row.items.push(title+': '+options.body);row.items=row.items.slice(-3);}
    row.time=Date.now();await cache.put(key,Response.json(row));
    const keys=await cache.keys();for(const old of keys.slice(0,Math.max(0,keys.length-30)))await cache.delete(old);
    if(row.count>1&&kind!=='digest'){title='KipClub · '+(kind==='changes'?'изменения':'уведомления')+': '+row.count;options.body=row.items.join('\n');}
  }catch{/* Full/private Cache Storage: still show every userVisibleOnly push. */}
  return self.registration.showNotification(title,options);
}

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  // Serialize concurrent pushes so their persistent group history cannot overwrite itself.
  const display=pushQueue=pushQueue.catch(()=>{}).then(()=>groupedPush(data));
  event.waitUntil(display.then(()=>receipt(data.broadcast_id,'shown')));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  let target = new URL('/', self.location.origin);
  try { const u = new URL(event.notification.data?.url || '/', self.location.origin); if (u.origin === self.location.origin) target = u; } catch { /* оставляем / */ }
  event.waitUntil(Promise.all([receipt(event.notification.data?.broadcast_id,'opened'), (async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      const current = new URL(client.url);
      if (target.searchParams.has('release') && current.pathname.startsWith('/admin/')) continue;
      if (current.origin === self.location.origin && 'focus' in client) {
        await client.focus();
        if ('navigate' in client) { try { await client.navigate(target.href); } catch { /* ignore */ } }
        return;
      }
    }
    await self.clients.openWindow(target.href);
  })()]));
});

/* Подписку отозвал браузер (смена ключей / срок): тихо пересоздаём на те же кружки, если сервер даёт ключ. */
self.addEventListener('pushsubscriptionchange', event => {
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(PUSH_PREFS_CACHE);
      const saved = await cache.match(new Request(new URL(PUSH_PREFS_KEY, self.location.origin)));
      const previous = event.oldSubscription?.endpoint;
      let prefs = saved ? await saved.json() : null;
      if (!prefs || (previous && prefs.endpoint !== previous)) prefs = previous ? { endpoint: previous, ...await pushStatus(previous) } : null;
      if (!prefs || (!prefs.general && !prefs.all && !prefs.club_ids?.length)) return; // нет согласия — не подписываем на всё
      const { publicKey } = await (await fetch('/api/push/vapid-public-key')).json();
      const pad = '='.repeat((4 - (publicKey.length % 4)) % 4);
      const raw = atob((publicKey + pad).replace(/-/g, '+').replace(/_/g, '/'));
      const key = Uint8Array.from(raw, c => c.charCodeAt(0));
      const sub = event.newSubscription || await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      const json = sub.toJSON();
      const post = async (path, body) => {
        const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!response.ok) throw new Error('push restore failed');
      };
      const flags = { announcements: prefs.announcements !== false, cancellations: prefs.cancellations !== false, moves: prefs.moves !== false };
      if (prefs.general && !prefs.all) {
        await post('/api/push/sync', { endpoint: json.endpoint, keys: json.keys, club_ids: prefs.club_ids || [], ...flags });
      } else {
        for (const club_id of prefs.all ? [null] : prefs.club_ids) await post('/api/push/subscribe', { endpoint: json.endpoint, keys: json.keys, club_id });
        await post('/api/push/preferences', { endpoint: json.endpoint, ...flags });
      }
      if (prefs.schedule_settings) await post('/api/push/schedule-settings', {endpoint:json.endpoint,...prefs.schedule_settings});
      await savePushPreferences(json.endpoint, await pushStatus(json.endpoint), prefs.schedule_settings);
      if (previous && previous !== json.endpoint) await post('/api/push/unsubscribe', { endpoint: previous });
    } catch { /* повторно предложим подписаться на странице кружка */ }
  })());
});
