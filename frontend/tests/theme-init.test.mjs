// theme-init.js — классический скрипт; исполняем в песочнице vm с минимальным «окном».
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../js/theme-init.js', import.meta.url)), 'utf8');

function makeWindow({ stored, systemDark = false, ua = 'Mozilla/5.0 (X11; Linux x86_64)', search = '', touch = 0, capacitor, session = {}, storageThrows = false } = {}) {
  const attrs = {};
  const metas = {};
  const store = new Map(stored === undefined ? [] : [['clubs.prefs', typeof stored === 'string' ? stored : JSON.stringify(stored)]]);
  const sess = new Map(Object.entries(session));
  const listeners = {};
  const mqListeners = [];
  const mq = { matches: systemDark, addEventListener: (_, fn) => mqListeners.push(fn) };
  const win = {
    document: {
      documentElement: { className: 'keep-me', setAttribute: (k, v) => { attrs[k] = v; } },
      head: { appendChild: m => { metas[m.name] = m; } },
      querySelector: sel => metas[/name="([^"]+)"/.exec(sel)?.[1]] ?? null,
      createElement: () => { const m = { setAttribute(k, v) { if (k === 'name') m.name = v; else m[k] = v; } }; return m; },
    },
    localStorage: storageThrows ? { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } }
      : { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    sessionStorage: { getItem: k => sess.get(k) ?? null, setItem: (k, v) => sess.set(k, v) },
    matchMedia: () => mq,
    navigator: { userAgent: ua, maxTouchPoints: touch },
    location: { search },
    URLSearchParams,
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    dispatchEvent: () => true,
    addEventListener: (type, fn) => { (listeners[type] ??= []).push(fn); },
    Capacitor: capacitor,
  };
  vm.runInNewContext(SRC, win);
  return { win, attrs, metas, store, mq, mqListeners, listeners, theme: win.ClubsTheme };
}

test('по умолчанию: системная светлая тема, акцент brick, обычный размер, desktop', () => {
  const { attrs, win } = makeWindow();
  assert.equal(attrs['data-theme'], 'light');
  assert.equal(attrs['data-theme-pref'], 'system');
  assert.equal(attrs['data-accent'], 'brick');
  assert.equal(attrs['data-text-size'], 'normal');
  assert.match(win.document.documentElement.className, /keep-me/);
  assert.match(win.document.documentElement.className, /platform-desktop/);
});

test('системная тёмная тема при режиме «Системная»; явный выбор сильнее системы', () => {
  assert.equal(makeWindow({ systemDark: true }).attrs['data-theme'], 'dark');
  assert.equal(makeWindow({ systemDark: true, stored: { theme: 'light' } }).attrs['data-theme'], 'light');
  assert.equal(makeWindow({ systemDark: false, stored: { theme: 'dark' } }).attrs['data-theme'], 'dark');
});

test('смена системной темы на лету подхватывается только в режиме «Системная»', () => {
  const sys = makeWindow({ systemDark: false });
  sys.mq.matches = true;
  sys.mqListeners.forEach(fn => fn());
  assert.equal(sys.attrs['data-theme'], 'dark');
  const fixed = makeWindow({ systemDark: false, stored: { theme: 'light' } });
  fixed.mq.matches = true;
  fixed.mqListeners.forEach(fn => fn());
  assert.equal(fixed.attrs['data-theme'], 'light');
});

test('set(): сохраняет в localStorage, обновляет атрибуты и theme-color, шлёт событие подписчикам', () => {
  const { theme, attrs, store, metas } = makeWindow();
  const seen = [];
  theme.onChange(s => seen.push(s));
  theme.set({ theme: 'dark', accent: 'blue', textSize: 'large' });
  assert.equal(attrs['data-theme'], 'dark');
  assert.equal(attrs['data-accent'], 'blue');
  assert.equal(attrs['data-text-size'], 'large');
  assert.deepEqual(JSON.parse(store.get('clubs.prefs')), { theme: 'dark', accent: 'blue', textSize: 'large' });
  assert.equal(metas['theme-color'].content, theme.THEME_COLOR.dark);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].resolved, 'dark');
});

test('мусор в localStorage и неизвестные значения → значения по умолчанию', () => {
  assert.equal(makeWindow({ stored: '{oops' }).attrs['data-theme-pref'], 'system');
  const { attrs } = makeWindow({ stored: { theme: 'neon', accent: '<script>', textSize: 999 } });
  assert.equal(attrs['data-theme-pref'], 'system');
  assert.equal(attrs['data-accent'], 'brick');
  assert.equal(attrs['data-text-size'], 'normal');
});

test('localStorage недоступен (приватный режим): работает, не падает', () => {
  const { theme, attrs } = makeWindow({ storageThrows: true });
  assert.equal(attrs['data-theme'], 'light');
  assert.doesNotThrow(() => theme.set({ theme: 'dark' }));
  assert.equal(attrs['data-theme'], 'dark');
});

test('платформа: UA Android / iPhone / iPadOS «как Mac» / десктоп', () => {
  assert.equal(makeWindow({ ua: 'Mozilla/5.0 (Linux; Android 14; Pixel 8)' }).theme.platform, 'android');
  assert.equal(makeWindow({ ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)' }).theme.platform, 'ios');
  assert.equal(makeWindow({ ua: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', touch: 5 }).theme.platform, 'ios');
  assert.equal(makeWindow({ ua: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', touch: 0 }).theme.platform, 'desktop');
});

test('платформа: ?platform= сильнее UA, запоминается на сессию; Capacitor сильнее UA', () => {
  assert.equal(makeWindow({ search: '?platform=ios' }).theme.platform, 'ios');
  assert.equal(makeWindow({ session: { 'clubs.platform': 'android' } }).theme.platform, 'android');
  assert.equal(makeWindow({ search: '?platform=hax' }).theme.platform, 'desktop');
  assert.equal(makeWindow({ capacitor: { getPlatform: () => 'android' } }).theme.platform, 'android');
});

test('нативные бары Capacitor синхронизируются (без плагина — тихо)', () => {
  const calls = [];
  const sb = { setStyle: o => { calls.push(['style', o.style]); return Promise.resolve(); }, setBackgroundColor: o => { calls.push(['bg', o.color]); return Promise.resolve(); } };
  const { theme } = makeWindow({ capacitor: { getPlatform: () => 'android', Plugins: { StatusBar: sb } }, stored: { theme: 'dark' } });
  assert.deepEqual(calls[0], ['style', 'DARK']);
  assert.equal(calls[1][0], 'bg');
  assert.doesNotThrow(() => theme.set({ theme: 'light' }));
  assert.doesNotThrow(() => makeWindow({ capacitor: { getPlatform: () => 'android' } }));
});
