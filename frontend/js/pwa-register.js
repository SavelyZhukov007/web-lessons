// Регистрирует service worker (офлайн-оболочка + push). Тихо ничего не делает там, где SW недоступны
// (http без localhost, старые браузеры, приватный режим Firefox).
import './ping.js';
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(error => console.warn('Service worker не зарегистрирован:', error));
  });
}

// Автообновление (в т.ч. iPhone «На экран Домой» по http, где SW нет): при возврате в приложение сверяем
// /build-info.json с тем, что было при загрузке, и при новой сборке перезагружаем страницу.
let loadedBuild = null;
async function currentBuild() {
  try { const r = await fetch('/build-info.json', { cache: 'no-store' }); return r.ok ? (await r.json()).build_id || null : null; }
  catch { return null; }
}
currentBuild().then(id => { loadedBuild = id; });
document.addEventListener('visibilitychange', async () => {
  if (document.hidden || !loadedBuild) return;
  const id = await currentBuild();
  if (id && id !== loadedBuild && !document.querySelector('dialog[open], form :focus')) location.reload();
});
// новый SW взял управление (skipWaiting + clients.claim) — один раз перезагрузиться на свежую оболочку
if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
  let reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (!reloaded) { reloaded = true; location.reload(); } });
}
