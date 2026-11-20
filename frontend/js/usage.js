// Обезличенная статистика (docs/privacy.md). Включена по умолчанию, выключатель «Анонимная статистика» в настройках.
// Уровень А: счётчики {metric, dim} из закрытых списков, версия, канал и платформа; без id, текста поиска, сообщений и стека.
// Уровень Б: раз в день POST /api/app/ping со случайным id установки (сервер хранит только HMAC). Выключатель гасит оба.
export const SWITCH_KEY = 'kc.anonymousUsage.v1'; // '0' = выключено пользователем; нет значения или '1' = включено
export const CONSENT_KEY = SWITCH_KEY; // старое имя (v1.9.023 и раньше)
export const QUEUE_KEY = 'kc.usageQueue.v1';
export const ID_KEY = 'kc.installId', PING_KEY = 'kc.pingAt';
export const QUEUE_MAX = 200, BATCH_MAX = 50;
export const METRICS = new Set(['page_open','app_open','app_resume','screen_view','schedule_view','schedule_nav','club_view','fav_add','fav_remove',
  'search_open','search_results','search_pick','search_abandon','filter_apply','calendar_export','calendar_fail','tour_open','share','print',
  'install_banner','install_open','install_download','install_prompt_available','install_prompt','install_accept','install_decline','installed','standalone_open',
  'ios_guide_open','ios_guide_step','ios_first_standalone','apk_page','apk_download','apk_first_run','update_offer','update_accept','update_later','update_done',
  'push_shown','push_open','push_dismiss','push_permission','push_subscribe','push_unsubscribe','api_error','native_crash','offline_open','offline_view_stale','load_source',
  'fb_prompt_shown','fb_rating','fb_prompt_dismiss','fb_prompt_snooze','fb_form_open','fb_sent']);
const API_ENDPOINTS = ['schedule','clubs','club','reference','announcements','push','feedback','app','admin','other'];
export const DIMS = new Set(['none','other','online','offline','cold','warm','home','week','day','club','clubs','my','settings','install','print','whats_new','admin',
  'today','tomorrow','day_other','week_this','week_next','week_other','swipe','tap','datepicker','category','room','leader','format','one','few','many','event',
  'web','ios','fcm','android','granted','denied','default','1','2','3','4','5','prompt_usage','prompt_update','prompt_error','shake','error',
  'cache','network','d0','d1','d2_7','d8p','webview','ui','net','storage',
  ...API_ENDPOINTS.flatMap(e => ['4xx','5xx','net'].map(c => `${e}_${c}`)), ...[1,2,3,4,5,6,7,8].map(i => `step${i}`)]);
export const validDim = dim => DIMS.has(dim) || /^c\d{1,6}$/.test(dim) || /^\d{1,2}\.\d{1,2}\.\d{3}$/.test(dim);
const PERF = new Set(['lcp','inp','cls','ttfb','fcp','ttfs']);
const CODES = new Set(['Error','TypeError','ReferenceError','SyntaxError','RangeError','URIError','EvalError','ResourceError','UnhandledRejection']);
export const resultBucket = count => !count ? 'none' : count === 1 ? 'one' : count <= 5 ? 'few' : 'many';
// Скорость кладётся в корзины: <1 с, 1..2,5 с, 2,5..4 с, >4 с. CLS: хорошо (<0,1), терпимо (<0,25), плохо.
export const perfBucket = (metric, value) => metric === 'cls' ? (value < .1 ? 'b1' : value < .25 ? 'b2' : 'b3')
  : value < 1000 ? 'b1' : value < 2500 ? 'b2' : value < 4000 ? 'b3' : 'b4';
export function apiErrorDim(path, status) {
  let p = '';
  try { p = new URL(path, 'http://local/').pathname; } catch { p = ''; }
  const ep = /^\/api\/schedule/.test(p) ? 'schedule' : /^\/api\/clubs\/\d+/.test(p) ? 'club' : /^\/api\/clubs/.test(p) ? 'clubs'
    : /^\/api\/(categories|leaders|rooms)/.test(p) ? 'reference' : /^\/api\/announcements/.test(p) ? 'announcements'
      : /^\/api\/push/.test(p) ? 'push' : /^\/api\/feedback/.test(p) ? 'feedback' : /^\/api\/app/.test(p) ? 'app' : /^\/api\/admin/.test(p) ? 'admin' : 'other';
  return `${ep}_${!status ? 'net' : status >= 500 ? '5xx' : '4xx'}`;
}
export function errorSignature(event) {
  const raw = event?.filename || event?.target?.src || '';
  let source = 'unknown';
  try { const name = new URL(raw, 'http://local/').pathname.split('/').pop(); if (/^[A-Za-z0-9_.-]{1,96}\.(?:m?js|css)$/.test(name)) source = name; } catch { /* no arbitrary text */ }
  return { code: CODES.has(event?.error?.name) ? event.error.name : event?.type === 'unhandledrejection' ? 'UnhandledRejection' : event?.target?.src ? 'ResourceError' : 'Error', source,
    line: Number.isInteger(event?.lineno) ? Math.min(1000000, Math.max(0, event.lineno)) : 0 };
}
export function usagePlatform(win) {
  if (win.Capacitor?.isNativePlatform?.()) return 'android';
  const standalone = win.navigator?.standalone || win.matchMedia?.('(display-mode: standalone)')?.matches;
  return standalone ? /iphone|ipad|ipod/i.test(win.navigator?.userAgent || '') ? 'ios' : 'pwa' : 'web';
}
export const pingKind = platform => ({ ios: 'ios-pwa', pwa: 'pwa', android: 'android' })[platform] || 'web';
export function usageChannel(win) {
  const c = String(win.ITC_CHANNEL || '');
  if (/^[pil]$/.test(c)) return c;
  const host = win.location?.hostname || '';
  if (host === 'lekora.ru' || win.location?.port === '7443') return 'i';
  if (!host || host === 'localhost' || /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) || host.endsWith('.local')) return 'l';
  return 'p';
}
export const shortVersion = v => String(v || '').match(/^v?(\d{1,2}\.\d{1,2}\.\d{3})/)?.[1] || '';

// Service worker сам не видит localStorage: сообщаем ему выключатель (пуш-квитанции и счётчики пушей)
// Выключатель уходит и в service worker (квитанции и счётчики пушей), и в APK (нативные квитанции пушей)
export function tellWorker(win, on) {
  try { win.navigator?.serviceWorker?.controller?.postMessage({ type: 'kc:usage-switch', on }); } catch { /* нет SW */ }
  try { win.Capacitor?.Plugins?.ItcNative?.setUsage?.({ enabled: on })?.catch?.(() => {}); } catch { /* не APK */ }
}
export function createUsage(win, { build = 'local', version = '' } = {}) {
  let queue = [], errors = [], perf = [], batch, timer, controller, inFlight, failures = 0, generation = 0, ver = shortVersion(version);
  const seenErrors = new Set(), seenPerf = new Set();
  const store = win.localStorage;
  const enabled = () => { try { return store.getItem(SWITCH_KEY) !== '0'; } catch { return false; } };
  const excluded = () => /^\/admin(?:\/|$)/.test(win.location?.pathname || '') || !!win.DemoBackend;
  const allowed = () => enabled() && !excluded();
  const persist = () => { try { if (queue.length) store.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-QUEUE_MAX))); else store.removeItem(QUEUE_KEY); } catch { /* storage full */ } };
  try { const saved = JSON.parse(store.getItem(QUEUE_KEY) || '[]'); if (Array.isArray(saved)) queue = saved.filter(e => METRICS.has(e?.metric) && validDim(e?.dim)).slice(-QUEUE_MAX); } catch { queue = []; }
  const schedule = (delay = 10000) => { if (!timer && allowed()) timer = win.setTimeout(() => { timer = null; flush(); }, delay); };
  function emit(metric, dim = 'none') {
    dim = String(dim);
    if (!allowed() || !METRICS.has(metric) || !validDim(dim)) return false;
    queue.push({ metric, dim });
    if (queue.length > QUEUE_MAX) queue.splice(0, queue.length - QUEUE_MAX); // офлайн-очередь до 200 событий
    persist(); schedule();
    return true;
  }
  function measure(metric, value) {
    if (!allowed() || !PERF.has(metric) || !Number.isFinite(value) || value < 0 || seenPerf.has(metric)) return false;
    seenPerf.add(metric); perf.push({ metric, bucket: perfBucket(metric, value) }); schedule();
    return true;
  }
  function error(event) {
    if (!allowed()) return;
    const row = errorSignature(event), key = JSON.stringify(row);
    if (seenErrors.has(key) || seenErrors.size >= 20) return;
    seenErrors.add(key); errors.push(row); schedule();
  }
  const apiError = (path, status) => emit('api_error', apiErrorDim(path, status));
  function setEnabled(value) {
    try { store.setItem(SWITCH_KEY, value ? '1' : '0'); } catch { return false; }
    tellWorker(win, !!value);
    generation++; controller?.abort(); win.clearTimeout(timer); timer = null;
    queue = []; errors = []; perf = []; batch = null; failures = 0; seenErrors.clear(); persist();
    if (value) emit('page_open', pageBucket(win.location?.pathname));
    return enabled();
  }
  function installId() {
    try {
      let id = store.getItem(ID_KEY);
      if (!id) { const b = new Uint8Array(16); win.crypto.getRandomValues(b); id = Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); store.setItem(ID_KEY, id); }
      return id;
    } catch { return null; }
  }
  // Уровень Б: «я пользуюсь» раз в день и при возврате (не чаще раза в час). Выключатель гасит и его.
  function ping(force = false, now = Date.now()) {
    if (!allowed() || win.navigator?.onLine === false) return false;
    const id = installId(); if (!id) return false;
    let last = 0; try { last = +store.getItem(PING_KEY) || 0; } catch { /* ignore */ }
    const newDay = new Date(now).toDateString() !== new Date(last).toDateString();
    if (!newDay && !(force && now - last > 3600e3)) return false;
    try { store.setItem(PING_KEY, String(now)); } catch { /* ignore */ }
    const body = { install_id: id, kind: pingKind(usagePlatform(win)), channel: usageChannel(win) };
    if (ver) body.version = ver;
    win.fetch('/api/app/ping', { method: 'POST', credentials: 'omit', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .catch(() => { try { store.setItem(PING_KEY, String(last)); } catch { /* ignore */ } });
    return true;
  }
  async function flush() {
    if (!allowed() || win.navigator?.onLine === false) return false;
    if (inFlight) return inFlight;
    win.clearTimeout(timer); timer = null;
    if (!batch) {
      if (!queue.length && !errors.length && !perf.length) return true;
      const bytes = new Uint8Array(16); win.crypto.getRandomValues(bytes);
      batch = { batch_id: Array.from(bytes, x => x.toString(16).padStart(2,'0')).join(''), platform: usagePlatform(win), channel: usageChannel(win),
        version: ver, build, events: queue.splice(0, BATCH_MAX), errors: errors.splice(0,20), perf: perf.splice(0, 20) };
      persist();
    }
    const own = batch, epoch = generation;
    controller = new AbortController();
    const timeout = win.setTimeout(() => controller?.abort(), 5000);
    inFlight = (async () => {
      try {
        const response = await win.fetch('/api/app/usage', { method:'POST', credentials:'omit', keepalive:true,
          headers:{'Content-Type':'application/json'}, body:JSON.stringify(own), signal:controller.signal });
        if (!response.ok) throw Error('metrics unavailable');
        if (epoch === generation) { batch = null; failures = 0; }
        return true;
      } catch {
        if (epoch === generation && ++failures >= 3) { batch = null; failures = 0; } // сервер не принимает: не копим бесконечно
        return false;
      } finally {
        win.clearTimeout(timeout); inFlight = null;
        if (epoch === generation && (batch || queue.length || errors.length || perf.length)) schedule(30000);
      }
    })();
    return inFlight;
  }
  // update_done: версия изменилась с прошлого открытия (dim: новая версия из справочника версий)
  function noteVersion() {
    if (!ver) return;
    let prev = ''; try { prev = store.getItem('kc.lastVersion') || ''; store.setItem('kc.lastVersion', ver); } catch { return; }
    if (prev && prev !== ver) emit('update_done', ver);
  }
  noteVersion();
  const setVersion = v => { const before = ver; ver = shortVersion(v) || ver; if (ver !== before) noteVersion(); };
  return { enabled, setEnabled, consent: enabled, setConsent: setEnabled, emit, measure, error, apiError, flush, ping, setVersion,
    version: () => ver, pending: () => queue.length };
}
export function pageBucket(path = '/') {
  return path === '/' || path === '/index.html' ? 'home' : /^\/club(?:[./]|$)/.test(path) ? 'club' : /^\/clubs(?:[./]|$)/.test(path) ? 'clubs'
    : /^\/(?:ios|android|install)(?:[./]|$)/.test(path) ? 'install' : /^\/print(?:[./]|$)/.test(path) ? 'print' : /^\/offline(?:[./]|$)/.test(path) ? 'offline' : 'other';
}
// Длина «устаревания» кэша для офлайна
export const staleDim = days => days <= 0 ? 'd0' : days === 1 ? 'd1' : days <= 7 ? 'd2_7' : 'd8p';

function observePerf(win, usage) {
  const PO = win.PerformanceObserver; if (!PO) return;
  const nav = win.performance?.getEntriesByType?.('navigation')?.[0];
  if (nav) {
    if (nav.responseStart > 0) usage.measure('ttfb', nav.responseStart);
    usage.emit('load_source', nav.transferSize === 0 || nav.deliveryType === 'cache' || win.navigator?.serviceWorker?.controller ? 'cache' : 'network');
  }
  let lcp = 0, cls = 0, inp = 0;
  const watch = (type, fn, opts = {}) => { try { new PO(list => list.getEntries().forEach(fn)).observe({ type, buffered: true, ...opts }); } catch { /* not supported */ } };
  watch('paint', e => { if (e.name === 'first-contentful-paint') usage.measure('fcp', e.startTime); });
  watch('largest-contentful-paint', e => { lcp = Math.max(lcp, e.startTime); });
  watch('layout-shift', e => { if (!e.hadRecentInput) cls += e.value; });
  watch('event', e => { inp = Math.max(inp, e.duration || 0); }, { durationThreshold: 40 });
  const report = () => { if (lcp) usage.measure('lcp', lcp); usage.measure('cls', cls); if (inp) usage.measure('inp', inp); };
  win.addEventListener('pagehide', report, { once: true });
  win.document?.addEventListener('visibilitychange', () => { if (win.document.hidden) report(); });
}

export let usage;
if (typeof window !== 'undefined' && typeof document !== 'undefined' && !window.KipUsage) {
  const hash = import.meta.url.match(/\/assets\/([a-f0-9]{20})\//)?.[1];
  const nativeVersion = String(window.ITC_VERSION || window.ItcSplash?.version || '');
  usage = createUsage(window, { build: /^[A-Za-z0-9_.-]{1,64}$/.test(nativeVersion) ? nativeVersion : hash || 'local', version: nativeVersion });
  window.KipUsage = usage;
  tellWorker(window, usage.enabled());
  navigator.serviceWorker?.addEventListener?.('controllerchange', () => tellWorker(window, usage.enabled()));
  if (!usage.version()) fetch('/release-info.json').then(r => r.ok ? r.json() : null).then(d => { if (d?.version) usage.setVersion(d.version); }).catch(() => {}).finally(() => usage.ping(false));
  else usage.ping(false);
  const once = new Set();
  const onceEmit = (metric, dim) => { if (!once.has(metric + dim)) { once.add(metric + dim); usage.emit(metric, dim); } };
  usage.emit('page_open', pageBucket(location.pathname));
  usage.emit('screen_view', pageBucket(location.pathname) === 'other' ? 'other' : pageBucket(location.pathname));
  usage.emit('app_open', navigator.onLine === false ? 'offline' : 'online');
  if (usagePlatform(window) !== 'web') usage.emit('standalone_open');
  if (usagePlatform(window) === 'ios') { try { if (!localStorage.getItem('kc.iosStandaloneSeen')) { localStorage.setItem('kc.iosStandaloneSeen', '1'); usage.emit('ios_first_standalone'); } } catch { /* ignore */ } }
  if (/^\/android(?:\/|$)/.test(location.pathname)) usage.emit('apk_page');
  if (/^\/ios(?:\/|$)/.test(location.pathname)) usage.emit('ios_guide_open');
  observePerf(window, usage);
  window.addEventListener('error', event => usage.error(event), true);
  window.addEventListener('unhandledrejection', event => usage.error(event));
  window.addEventListener('online', () => { usage.flush(); usage.ping(true); });
  window.addEventListener('storage', event => { if (event.key === SWITCH_KEY && !usage.enabled()) usage.setEnabled(false); });
  window.addEventListener('pagehide', () => queueMicrotask(() => usage.flush()));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) queueMicrotask(() => usage.flush());
    else { usage.emit('app_resume', navigator.onLine === false ? 'offline' : 'warm'); usage.ping(true); }
  });
  window.addEventListener('beforeinstallprompt', () => onceEmit('install_prompt_available', 'none'));
  window.addEventListener('appinstalled', () => onceEmit('installed', 'none'));
  window.addEventListener('kc:usage', event => {
    const { metric, dim } = event.detail || {};
    if (metric === 'install_banner') onceEmit('install_banner', 'none'); else if (metric) usage.emit(metric, dim);
  });
  if (document.querySelector('.install-banner')) onceEmit('install_banner', 'none');
  // Делегированные клики: ссылки установки, календарь, 3D-тур, печать и элементы с data-usage="metric:dim"
  document.addEventListener('click', event => {
    const tagged = event.target.closest?.('[data-usage]');
    if (tagged) { const [metric, dim = 'none'] = tagged.dataset.usage.split(':'); usage.emit(metric, dim); }
    const link = event.target.closest?.('a'); if (!link) return;
    let url; try { url = new URL(link.href, location.href); } catch { return; }
    const path = url.pathname;
    if (/^\/(?:ios|android|install)(?:\/|\.html|$)/.test(path)) {
      if (path === '/android/download') { onceEmit('install_download', 'none'); usage.emit('apk_download'); } else onceEmit('install_open', 'none');
    } else if (/\/calendar\.ics$/.test(path)) usage.emit('calendar_export', url.searchParams.has('start') ? 'club' : link.closest('.event-card, [data-event-id]') ? 'one' : 'week');
    else if (/tour\.panoee\.net$/.test(url.hostname)) usage.emit('tour_open', link.closest('#settings-dialog, .itc-group, [data-campus-tour]') ? 'settings' : 'event');
    else if (/^\/print(?:\.html)?$/.test(path)) usage.emit('print');
  }, { passive:true, capture:true });
}
