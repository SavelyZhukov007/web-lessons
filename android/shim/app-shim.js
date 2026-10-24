/* Shim для Android-клиента. Подключается ПЕРЕД js/api.js (prepare-web вставляет его в <head>).
 * 1) хранит адрес сервера (localStorage), 2) переписывает fetch('/api/...') -> '<server>/api/...',
 * 3) при первом запуске ведёт на /settings.html, 4) рисует кнопку «Сервер» для смены адреса.
 * api.js и остальной код сайта не изменены. */
(function () {
  'use strict';
  var KEY = 'clubs.serverUrl';
  var API_PREFIXES = ['/api/'];

  function normalize(raw) {
    var s = String(raw == null ? '' : raw).trim();
    if (!s) throw new Error('Введи адрес сервера, например http://192.168.1.50:8000');
    var bare = !/^[a-z][a-z0-9+.-]*:\/\//i.test(s);
    if (bare) s = 'http://' + s;
    var u;
    try { u = new URL(s); if (bare && !u.port && !/:\d+(\/|$)/.test(s.slice(7))) u.port = '8000'; } catch (e) { throw new Error('Некорректный адрес. Пример: http://192.168.1.50:8000'); }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('Поддерживаются только http:// и https://');
    if (!u.hostname || !/^(\[[0-9a-f:.]+\]|[a-z0-9]([a-z0-9._-]*[a-z0-9])?)$/i.test(u.hostname)) throw new Error('Некорректный хост или IP');
    if (u.port && (Number(u.port) < 1 || Number(u.port) > 65535)) throw new Error('Порт должен быть 1–65535');
    return u.origin; // без пути и без «/» на конце
  }
  function get() { try { return localStorage.getItem(KEY) || window.APP_DEFAULT_SERVER || ''; } catch (e) { return window.APP_DEFAULT_SERVER || ''; } } // APP_DEFAULT_SERVER — опционально, из `build android --server-url`
  function set(v) { localStorage.setItem(KEY, normalize(v)); return get(); }
  function clear() { try { localStorage.removeItem(KEY); } catch (e) {} }

  function withTimeout(promise, ms, message) {
    return new Promise(function (resolve, reject) {
      var t = setTimeout(function () { reject(new Error(message)); }, ms);
      promise.then(function (v) { clearTimeout(t); resolve(v); }, function (e) { clearTimeout(t); reject(e); });
    });
  }
  // Проверка соединения: /api/health, затем /api/clubs. Не зависит от сохранённого адреса.
  function test(raw) {
    var base;
    try { base = normalize(raw); } catch (e) { return Promise.reject(e); }
    var f = window.fetch.bind(window); // уже обёрнутый fetch не нужен: берём URL абсолютным
    return withTimeout(f(base + '/api/health', { cache: 'no-store' }), 8000,
      'Сервер не отвечает за 8 секунд. Проверь IP, порт, Wi‑Fi и что сервер запущен с --host 0.0.0.0.')
      .catch(function (e) {
        if (e && /8 секунд/.test(e.message)) throw e;
        throw new Error('Не удалось связаться с ' + base + '. Проверь IP/порт, что телефон в той же Wi‑Fi сети, сервер запущен с --host 0.0.0.0 и брандмауэр пропускает порт. (В браузере это также бывает CORS.)');
      })
      .then(function (r) {
        if (!r.ok) throw new Error('Сервер ответил HTTP ' + r.status + ' на /api/health — это точно сервер расписания?');
        return r.text().then(function (t) {
          var j; try { j = JSON.parse(t); } catch (e) { throw new Error('Ответ не похож на API расписания (не JSON). Проверь порт.'); }
          if (!j || j.status !== 'ok') throw new Error('Неожиданный ответ /api/health: ' + t.slice(0, 80));
          return f(base + '/api/clubs', { cache: 'no-store' });
        });
      })
      .then(function (r) { if (!r.ok) throw new Error('/api/clubs вернул HTTP ' + r.status); return r.json(); })
      .then(function (clubs) { return { base: base, clubs: Array.isArray(clubs) ? clubs.length : 0 }; });
  }

  // Опознание сервера: GET /api/app/info → {app:"itc-kruzhki", name, version, api_version, server_id}
  var API_VERSION = 1;
  function info(raw, ms) {
    var base;
    try { base = normalize(raw); } catch (e) { return Promise.reject(e); }
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    return withTimeout((window.ItcRawFetch || window.fetch)(base + '/api/app/info', { cache: 'no-store', signal: ctl && ctl.signal }), ms || 4000,
      'Сервер не ответил за ' + Math.round((ms || 4000) / 1000) + ' с. Проверь адрес, порт и что телефон в той же сети.')
      .catch(function (e) { if (ctl) ctl.abort(); if (e && / с\. /.test(e.message)) throw e;
        throw new Error('Не удалось связаться с ' + base + '. Проверь адрес и порт; в браузере причиной бывает CORS.'); })
      .then(function (r) {
        if (r.status === 404) throw new Error('По адресу ' + base + ' отвечает другой сервер (нет /api/app/info) — это не сервер «Кружков» или он устарел.');
        if (!r.ok) throw new Error('Сервер ответил HTTP ' + r.status);
        return r.json().catch(function () { throw new Error('Ответ не похож на сервер «Кружков» (не JSON).'); });
      })
      .then(function (j) {
        if (!j || j.app !== 'itc-kruzhki') throw new Error('Это другое приложение (' + (j && j.app || 'неизвестно') + '), а не сервер «Кружков».');
        return { base: base, name: j.name || base, version: j.version || '?', server_id: j.server_id || '', api_version: j.api_version,
          compatible: j.api_version === API_VERSION,
          warning: j.api_version === API_VERSION ? '' : 'Версия API сервера (' + j.api_version + ') отличается от приложения (' + API_VERSION + '): что-то может не работать.' };
      });
  }
  var api = { KEY: KEY, normalize: normalize, get: get, set: set, clear: clear, test: test, info: info, API_VERSION: API_VERSION };
  window.ItcServerTools = api;
  // демо-сборка без выбранного тестового сервера: только инструменты (подключение из Настроек), демо-бэкенд работает как раньше
  if (window.APP_DEMO_BUILD && !localStorage.getItem(KEY)) return;
  window.AppServer = api;

  var onSettings = location.pathname === '/settings.html';
  var base = get();

  // --- fetch: относительные /api/... -> абсолютный адрес сервера
  var origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = function (input, init) {
      if (typeof input === 'string' && base && API_PREFIXES.some(function (p) { return input.indexOf(p) === 0; })) {
        input = base + input; // админка в приложении ходит по Bearer-токену (cookie между origin не нужны; CORS без credentials)
      }
      return origFetch.call(window, input, init);
    };
  }
  // ссылки на /api/... (например, будущий .ics) тоже ведём на сервер
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href^="/api/"]');
    if (a && base) { e.preventDefault(); location.href = base + a.getAttribute('href'); }
  }, true);

  // --- первый запуск
  if (!base && !onSettings) { location.replace('/settings.html?first=1'); return; }

  // --- кнопка смены сервера
  function addGear() {
    if (onSettings || !document.body) return;
    if (document.querySelector('[data-settings-button]')) return; // сайт уже имеет свою кнопку «Настройки» (там же блок «Сервер»)
    var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/css/app-shell.css'; document.head.appendChild(l);
    var a = document.createElement('a');
    a.className = 'app-gear'; a.href = '/settings.html'; a.id = 'app-gear';
    a.setAttribute('aria-label', 'Сменить сервер: ' + base);
    var host = base.replace(/^https?:\/\//, '');
    a.innerHTML = '<span aria-hidden="true">⚙</span><small></small>';
    a.querySelector('small').textContent = host;
    document.body.appendChild(a);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addGear); else addGear();
})();
