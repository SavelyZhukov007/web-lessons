const CHECK_INTERVAL = 60_000;
export function hasUnsavedWork(doc = document) {
  return !!doc.querySelector('dialog[open], [data-unsaved="true"], [data-update-busy="true"]');
}

export function startUpdates() {
  if (window.Capacitor?.isNativePlatform?.() || window.ClubsUpdates) return;
  let registration, pending = false, nextBuild = null, loadedBuild = null, checking, lastCheck = 0, applying = false;
  let bar, message, button;
  const sw = navigator.serviceWorker;
  let hadController = !!sw?.controller;
  function notify(text) {
    if (!bar) {
      bar = document.createElement('aside'); bar.className = 'app-update-notice'; bar.setAttribute('aria-label', 'Обновление приложения');
      message = document.createElement('span'); message.setAttribute('role', 'status');
      button = document.createElement('button'); button.type = 'button'; button.textContent = 'Обновить'; button.addEventListener('click', apply);
      bar.append(message, button); document.body.append(bar);
    }
    bar.hidden = false; message.textContent = text; button.hidden = !pending; button.disabled = pending && hasUnsavedWork();
  }
  function showPending() {
    notify(hasUnsavedWork() ? 'Есть обновление. Сохраните или закройте форму — ввод не будет потерян.' : 'Доступна новая версия приложения.');
  }
  function reload() {
    if (hasUnsavedWork()) { applying = false; showPending(); return; }
    const target = new URL(location.href), id = nextBuild || loadedBuild || 'worker-update';
    try {
      if (sessionStorage.getItem('clubs.update.reload') === id) { applying = false; notify('Обновление уже загружалось. Закройте и снова откройте приложение, если версия не изменилась.'); return; }
      sessionStorage.setItem('clubs.update.reload', id);
    } catch { /* недоступно */ }
    target.searchParams.set('__clubs_update', id); location.replace(target.href);
  }
  async function apply() {
    if (!pending || applying) return;
    if (hasUnsavedWork()) { showPending(); return; }
    applying = true;
    if (registration?.waiting) { registration.waiting.postMessage({ type: 'clubs:activate' }); return; }
    reload();
  }
  async function buildId() {
    try {
      const response = await fetch(`/build-info.json?check=${Date.now()}`, { cache: 'no-store' });
      return response.ok ? (await response.json()).build_id || null : null;
    } catch { return null; }
  }
  async function check({ manual = false } = {}) {
    if (checking) return checking;
    if (!manual && Date.now() - lastCheck < CHECK_INTERVAL) return;
    lastCheck = Date.now();
    checking = (async () => {
      const id = await buildId();
      if (id && loadedBuild && id !== loadedBuild) { pending = true; nextBuild = id; }
      if (id && !loadedBuild) loadedBuild = id;
      try { await registration?.update(); } catch { /* нет связи */ }
      if (registration?.waiting) pending = true;
      if (pending) { showPending(); if (!hasUnsavedWork()) await apply(); }
      else if (manual) notify(id ? 'Установлена актуальная версия.' : 'Не удалось проверить версию. Проверьте подключение.');
      return { available: pending, build: id };
    })().finally(() => { checking = null; });
    return checking;
  }
  window.ClubsUpdates = { check, apply };
  const cleanUrl = new URL(location.href);
  if (cleanUrl.searchParams.has('__clubs_update')) {
    loadedBuild = cleanUrl.searchParams.get('__clubs_update');
    cleanUrl.searchParams.delete('__clubs_update'); history.replaceState(history.state, '', cleanUrl.href);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  window.addEventListener('pageshow', () => check());
  const reconsider = () => { if (pending) showPending(); };
  document.addEventListener('app:draft-change', reconsider);
  document.addEventListener('close', reconsider, true);
  if (sw) sw.addEventListener('controllerchange', async () => {
    if (!hadController) { hadController = true; return; } // первый install уже соответствует открытой странице
    nextBuild = await buildId() || nextBuild;
    pending = true;
    if (hasUnsavedWork()) { applying = false; showPending(); } else if (applying || loadedBuild) reload();
  });
  async function boot() {
    loadedBuild ||= await buildId();
    if (sw && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) {
      try {
        registration = await sw.register('/sw.js', { scope: '/', updateViaCache: 'none' });
        if (registration.waiting) { pending = true; showPending(); }
        registration.addEventListener('updatefound', () => {
          const worker = registration.installing;
          worker?.addEventListener('statechange', () => {
            if (worker.state === 'installed' && sw.controller) { pending = true; showPending(); if (!hasUnsavedWork()) apply(); }
          });
        });
      } catch (error) { console.warn('Service worker не зарегистрирован:', error); }
    }
    check();
  }
  if (document.readyState === 'complete') boot(); else window.addEventListener('load', boot, { once: true });
}
