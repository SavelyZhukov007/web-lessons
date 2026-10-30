// Журнал устройства для «Обратной связи»: кольцевой буфер последних записей (ошибки/предупреждения консоли,
// необработанные ошибки и rejection, неудачные fetch с url/status/ms, переходы по страницам) + сведения об устройстве.
// Ничего не отправляет сам: снимок журнала автоматически прикладывается к обращению из формы обратной связи (без паролей и личных данных — см. scrub).
'use strict';

export const LIMIT = 200;
const SECRET = /((?:password|token|access_token|refresh_token|secret|authorization)["']?\s*[:=]\s*["']?)[^\s"',;&]+/gi;
const BEARER = /bearer\s+[a-z0-9._~+/=-]{8,}/gi;

export const scrub = text => String(text ?? '').replace(BEARER, 'Bearer [скрыто]').replace(SECRET, '$1[скрыто]').slice(0, 2000);
const stripQuery = url => { try { const u = new URL(url, 'http://x'); return u.origin === 'http://x' ? u.pathname : u.origin + u.pathname; } catch { return scrub(url).split('?')[0]; } };

export function createCollector({ limit = LIMIT, now = () => Date.now() } = {}) {
  const buf = [];
  const push = entry => { buf.push({ t: new Date(now()).toISOString(), ...entry }); if (buf.length > limit) buf.splice(0, buf.length - limit); };
  const fmt = args => args.map(a => a instanceof Error ? `${a.name}: ${a.message}` : typeof a === 'string' ? a : (() => { try { return JSON.stringify(a); } catch { return String(a); } })()).join(' ');
  return {
    push,
    console(level, args) { push({ level, kind: 'console', msg: scrub(fmt(args)) }); },
    error(msg, stack, src) { push({ level: 'error', kind: 'error', msg: scrub(msg), ...(stack ? { stack: scrub(stack) } : {}), ...(src ? { src: stripQuery(src) } : {}) }); },
    rejection(reason) { push({ level: 'error', kind: 'rejection', msg: scrub(reason instanceof Error ? `${reason.name}: ${reason.message}` : fmt([reason])), ...(reason?.stack ? { stack: scrub(reason.stack) } : {}) }); },
    fetch(url, status, ms, method = 'GET') { push({ level: status === 0 || status >= 500 ? 'error' : 'warn', kind: 'fetch', method, url: stripQuery(url), status, ms: Math.round(ms) }); },
    nav(url) { push({ level: 'info', kind: 'nav', url: stripQuery(url) }); },
    entries: () => buf.slice(),
    clear: () => { buf.length = 0; },
  };
}

// Полный идентификатор версии v<X.Y.Z><канал><стадия><платформа>, платформа W|M|A
export function platformLetter(win = globalThis) {
  if (win.Capacitor?.isNativePlatform?.()) return 'A';
  const standalone = win.navigator?.standalone || win.matchMedia?.('(display-mode: standalone)')?.matches;
  return standalone && /iphone|ipad|ipod/i.test(win.navigator?.userAgent || '') ? 'M' : 'W';
}
export function fullVersion(id, platform) {
  if (!id) return '';
  const v = String(id).startsWith('v') ? String(id) : `v${id}`;
  return /[WMA]$/.test(v) ? v : v + platform;
}

export async function deviceInfo(win = globalThis) {
  const platform = platformLetter(win);
  let build = win.ItcSplash?.version || '';
  if (!build && win.fetch) {
    try { const r = await win.fetch(`/build-info.json?fb=${Date.now()}`, { cache: 'no-store' }); if (r.ok) build = (await r.json()).build_id || ''; } catch { /* офлайн */ }
  }
  const info = {
    version: fullVersion(build, platform), platform, userAgent: win.navigator?.userAgent || '',
    screen: win.screen ? `${win.screen.width}x${win.screen.height}@${win.devicePixelRatio || 1}` : '',
    viewport: `${win.innerWidth || 0}x${win.innerHeight || 0}`, language: win.navigator?.language || '',
    online: win.navigator?.onLine !== false, page: win.location ? stripQuery(win.location.href) : '', time: new Date().toISOString(),
  };
  try { const D = win.Capacitor?.Plugins?.Device; if (D?.getInfo) info.device = await D.getInfo(); } catch { /* нет плагина */ }
  return info;
}

// Установка перехватчиков в браузере (один раз на страницу)
export function install(win = globalThis, collector = createCollector()) {
  if (win.__clubsLogs) return win.__clubsLogs;
  win.__clubsLogs = collector;
  for (const level of ['error', 'warn']) {
    const orig = win.console?.[level];
    if (orig) win.console[level] = (...args) => { try { collector.console(level, args); } catch { /* ignore */ } return orig.apply(win.console, args); };
  }
  win.addEventListener?.('error', e => collector.error(e.message || 'error', e.error?.stack, e.filename));
  win.addEventListener?.('unhandledrejection', e => collector.rejection(e.reason));
  const origFetch = win.fetch;
  if (origFetch) win.fetch = async (input, init) => {
    const started = Date.now();
    const url = typeof input === 'string' ? input : input?.url || String(input);
    const method = init?.method || input?.method || 'GET';
    try {
      const res = await origFetch.call(win, input, init);
      if (!res.ok) collector.fetch(url, res.status, Date.now() - started, method);
      return res;
    } catch (err) {
      if (err?.name !== 'AbortError') collector.fetch(url, 0, Date.now() - started, method);
      throw err;
    }
  };
  if (win.location) collector.nav(win.location.href);
  win.addEventListener?.('hashchange', () => collector.nav(win.location.href));
  win.addEventListener?.('popstate', () => collector.nav(win.location.href));
  return collector;
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') install(window);
