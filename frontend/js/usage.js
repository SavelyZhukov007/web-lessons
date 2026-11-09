// Opt-in anonymous aggregate events + technical signatures only; no identifier, query, message or stack.
export const CONSENT_KEY = 'kc.anonymousUsage.v1';
export const METRICS = new Set(['page_open','install_banner','install_open','install_download','install_prompt_available','install_prompt','install_accept','install_decline','installed','standalone_open','search_open','search_results','search_pick','search_abandon']);
const CODES = new Set(['Error','TypeError','ReferenceError','SyntaxError','RangeError','URIError','EvalError','ResourceError','UnhandledRejection']);
const BUCKETS = new Set(['none','one','few','many','home','club','clubs','install','other']);
export const resultBucket = count => !count ? 'none' : count === 1 ? 'one' : count <= 5 ? 'few' : 'many';
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
export function createUsage(win, { build = 'local' } = {}) {
  let queue = [], errors = [], batch, timer, controller, inFlight, failures = 0, generation = 0;
  const seenErrors = new Set();
  const consent = () => { try { return win.localStorage.getItem(CONSENT_KEY) === '1'; } catch { return false; } };
  const allowed = () => consent() && !/^\/admin(?:\/|$)/.test(win.location?.pathname || '') && !win.DemoBackend;
  const schedule = (delay = 10000) => { if (!timer && allowed()) timer = win.setTimeout(() => { timer = null; flush(); }, delay); };
  function emit(metric, bucket = 'none') {
    if (!allowed() || !METRICS.has(metric) || !BUCKETS.has(bucket)) return;
    if (queue.length < 60) queue.push({ metric, bucket });
    schedule();
  }
  function error(event) {
    if (!allowed()) return;
    const row = errorSignature(event), key = JSON.stringify(row);
    if (seenErrors.has(key) || seenErrors.size >= 20) return;
    seenErrors.add(key); errors.push(row); schedule();
  }
  function setConsent(value) {
    try { win.localStorage.setItem(CONSENT_KEY, value ? '1' : '0'); } catch { return false; }
    generation++; controller?.abort(); win.clearTimeout(timer); timer = null;
    queue = []; errors = []; batch = null; failures = 0; seenErrors.clear();
    if (value) emit('page_open', pageBucket(win.location?.pathname));
    return consent();
  }
  async function flush() {
    if (!allowed() || win.navigator?.onLine === false) return false;
    if (inFlight) return inFlight;
    win.clearTimeout(timer); timer = null;
    if (!batch) {
      if (!queue.length && !errors.length) return true;
      const bytes = new Uint8Array(16); win.crypto.getRandomValues(bytes);
      batch = { batch_id: Array.from(bytes, x => x.toString(16).padStart(2,'0')).join(''), platform: usagePlatform(win), build,
        events: queue.splice(0,20), errors: errors.splice(0,20) };
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
        if (epoch === generation && ++failures >= 3) { batch = null; failures = 0; }
        return false;
      } finally {
        win.clearTimeout(timeout); inFlight = null;
        if (epoch === generation && (batch || queue.length || errors.length)) schedule(30000);
      }
    })();
    return inFlight;
  }
  return { consent, setConsent, emit, error, flush };
}
export function pageBucket(path = '/') {
  return path === '/' || path === '/index.html' ? 'home' : /^\/club(?:[./]|$)/.test(path) ? 'club' : /^\/clubs(?:[./]|$)/.test(path) ? 'clubs' : /^\/(?:ios|android|install)(?:[./]|$)/.test(path) ? 'install' : 'other';
}
export let usage;
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  const hash = import.meta.url.match(/\/assets\/([a-f0-9]{20})\//)?.[1];
  const nativeBuild = String(window.ItcSplash?.version || '');
  usage = createUsage(window, { build: /^[A-Za-z0-9_.-]{1,64}$/.test(nativeBuild) ? nativeBuild : hash || 'local' });
  window.KipUsage = usage;
  const once = new Set();
  const installEvent = (metric) => { if (!once.has(metric)) { once.add(metric); usage.emit(metric); } };
  usage.emit('page_open', pageBucket(location.pathname));
  if (usagePlatform(window) !== 'web') usage.emit('standalone_open');
  window.addEventListener('error', event => usage.error(event), true);
  window.addEventListener('unhandledrejection', event => usage.error(event));
  window.addEventListener('online', () => usage.flush());
  window.addEventListener('storage', event => { if (event.key === CONSENT_KEY && !usage.consent()) usage.setConsent(false); });
  window.addEventListener('pagehide', () => queueMicrotask(() => usage.flush()));
  document.addEventListener('visibilitychange', () => { if (document.hidden) queueMicrotask(() => usage.flush()); });
  window.addEventListener('beforeinstallprompt', () => installEvent('install_prompt_available'));
  window.addEventListener('appinstalled', () => installEvent('installed'));
  window.addEventListener('kc:usage', event => { if (event.detail?.metric === 'install_banner') installEvent('install_banner'); });
  if (document.querySelector('.install-banner')) installEvent('install_banner');
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a'); if (!link) return;
    let path; try { path = new URL(link.href, location.href).pathname; } catch { return; }
    if (/^\/(?:ios|android|install)(?:\/|\.html|$)/.test(path)) installEvent(path === '/android/download' ? 'install_download' : 'install_open');
  }, { passive:true, capture:true });
}
