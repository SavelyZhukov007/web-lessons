/* Тема, акцент, размер текста и платформа. КЛАССИЧЕСКИЙ блокирующий скрипт в <head> (до CSS-отрисовки body),
   поэтому страница не «вспыхивает» белым в тёмной теме. Внешний файл — а не inline — из-за CSP (script-src 'self').
   Хранит настройки в localStorage['clubs.prefs'] и выставляет на <html>:
     data-theme="light|dark" (итог), data-theme-pref="system|light|dark", data-accent, data-text-size, class="platform-android|ios|desktop".
   Публичный API: window.ClubsTheme { get, set, resolved, platform, onChange, DEFAULTS, THEME_COLOR }. */
(function (root) {
  'use strict';
  var KEY = 'clubs.prefs';
  var THEMES = ['system', 'light', 'dark'];
  var ACCENTS = ['brick', 'blue', 'green', 'violet'];
  var SIZES = ['normal', 'large', 'xlarge'];
  var DEFAULTS = { theme: 'system', accent: 'brick', textSize: 'normal' };
  var THEME_COLOR = { light: '#ffffff', dark: '#111412' };
  var doc = root.document;
  var listeners = [];

  function pick(value, allowed, fallback) { return allowed.indexOf(value) >= 0 ? value : fallback; }
  function normalize(raw) {
    raw = raw && typeof raw === 'object' ? raw : {};
    return {
      theme: pick(raw.theme, THEMES, DEFAULTS.theme),
      accent: pick(raw.accent, ACCENTS, DEFAULTS.accent),
      textSize: pick(raw.textSize, SIZES, DEFAULTS.textSize)
    };
  }
  function load() {
    try { return normalize(JSON.parse(root.localStorage.getItem(KEY))); } catch (e) { return normalize(null); }
  }
  function save(prefs) { try { root.localStorage.setItem(KEY, JSON.stringify(prefs)); return true; } catch (e) { return false; } }

  function systemDark() {
    try { return !!(root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)').matches); } catch (e) { return false; }
  }
  function resolve(pref, isDark) { return pref === 'dark' ? 'dark' : pref === 'light' ? 'light' : (isDark ? 'dark' : 'light'); }

  // Платформа: ?platform=… (для проверки внешнего вида) > Capacitor > UA.
  function detectPlatform() {
    var q = '';
    try { q = new root.URLSearchParams(root.location.search).get('platform') || ''; } catch (e) {}
    if (q === 'ios' || q === 'android' || q === 'desktop') {
      try { root.sessionStorage.setItem('clubs.platform', q); } catch (e) {}
      return q;
    }
    try { var s = root.sessionStorage.getItem('clubs.platform'); if (s === 'ios' || s === 'android' || s === 'desktop') return s; } catch (e) {}
    try {
      if (root.Capacitor && typeof root.Capacitor.getPlatform === 'function') {
        var p = root.Capacitor.getPlatform();
        if (p === 'android' || p === 'ios') return p;
      }
    } catch (e) {}
    var nav = root.navigator || {};
    var ua = String(nav.userAgent || '');
    if (/Android/i.test(ua)) return 'android';
    if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
    if (/Macintosh/i.test(ua) && nav.maxTouchPoints > 1) return 'ios'; // iPadOS в режиме «как Mac»
    return 'desktop';
  }

  var platform = detectPlatform();
  var prefs = load();
  var resolved = resolve(prefs.theme, systemDark());

  function syncNative() {
    // Capacitor: цвет/стиль системных баров. Плагин опционален — без него просто ничего не делаем.
    try {
      var cap = root.Capacitor; var sb = cap && cap.Plugins && cap.Plugins.StatusBar;
      if (sb) {
        if (sb.setStyle) sb.setStyle({ style: resolved === 'dark' ? 'DARK' : 'LIGHT' }).catch(function () {});
        if (sb.setBackgroundColor && platform === 'android') sb.setBackgroundColor({ color: THEME_COLOR[resolved] }).catch(function () {});
      }
    } catch (e) {}
  }

  function apply() {
    resolved = resolve(prefs.theme, systemDark());
    var el = doc.documentElement;
    el.setAttribute('data-theme', resolved);
    el.setAttribute('data-theme-pref', prefs.theme);
    el.setAttribute('data-accent', prefs.accent);
    el.setAttribute('data-text-size', prefs.textSize);
    var cls = (el.className || '').split(/\s+/).filter(function (c) { return c && c.indexOf('platform-') !== 0; });
    cls.push('platform-' + platform);
    el.className = cls.join(' ');
    var meta = doc.querySelector && doc.querySelector('meta[name="theme-color"]');
    if (!meta && doc.head && doc.createElement) { meta = doc.createElement('meta'); meta.setAttribute('name', 'theme-color'); doc.head.appendChild(meta); }
    if (meta) meta.setAttribute('content', THEME_COLOR[resolved]);
    // PWA-сборка ставит пару theme-color с media (светлая/тёмная): явный выбор темы перекрывает обе, «системная» — возвращает по media
    var scoped = doc.querySelectorAll ? doc.querySelectorAll('meta[name="theme-color"][media]') : [];
    for (var i = 0; i < scoped.length; i++) {
      var media = scoped[i].getAttribute('media') || '';
      var own = media.indexOf('dark') >= 0 ? 'dark' : 'light';
      scoped[i].setAttribute('content', THEME_COLOR[prefs.theme === 'system' ? own : resolved]);
    }
    syncNative();
  }

  function emit() {
    var snapshot = { prefs: get(), resolved: resolved, platform: platform };
    listeners.slice().forEach(function (fn) { try { fn(snapshot); } catch (e) {} });
    try { root.dispatchEvent(new root.CustomEvent('clubs:themechange', { detail: snapshot })); } catch (e) {}
  }
  function get() { return { theme: prefs.theme, accent: prefs.accent, textSize: prefs.textSize }; }
  function set(partial) {
    prefs = normalize(Object.assign({}, prefs, partial));
    save(prefs); apply(); emit();
    return get();
  }
  function onChange(fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; }

  apply();
  try {
    var mq = root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)');
    var onSys = function () { if (prefs.theme === 'system') { apply(); emit(); } };
    if (mq) { if (mq.addEventListener) mq.addEventListener('change', onSys); else if (mq.addListener) mq.addListener(onSys); }
    // синхронизация между вкладками
    root.addEventListener && root.addEventListener('storage', function (e) { if (e.key === KEY) { prefs = load(); apply(); emit(); } });
  } catch (e) {}

  root.ClubsTheme = {
    get: get, set: set, onChange: onChange,
    resolved: function () { return resolved; },
    platform: platform,
    DEFAULTS: DEFAULTS, THEME_COLOR: THEME_COLOR, THEMES: THEMES, ACCENTS: ACCENTS, SIZES: SIZES,
    _normalize: normalize, _resolve: resolve, _detectPlatform: detectPlatform
  };
})(typeof window !== 'undefined' ? window : globalThis);
