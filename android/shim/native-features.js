/* Нативные функции APK (phase 2 C). Подключается prepare-web.mjs только в www/ приложения, после native-shell.js.
 * Вне Capacitor.isNativePlatform() ничего не делает — сайт не меняется.
 *  - «Мои кружки»: звёздочка на странице кружка и в каталоге, фильтр «Мои» в расписании (localStorage itc.follows)
 *  - напоминания и уведомления об отмене/переносе: настройки здесь, сама логика — в нативном плагине ItcNative
 *    (AlarmManager + WorkManager, без Google Play Services)
 *  - виджеты: данные передаются плагину при каждой синхронизации; кнопки «добавить виджет»
 *  - ярлыки/уведомления: ссылки itckruzhki://open/<путь> -> страница
 *  - офлайн-кэш: GET /api/* сохраняются, без сети отдаются из кэша, баннер «Нет сети»
 *  - объявления админа: нативный плагин сам забирает GET /api/announcements (при запуске и в фоне), здесь — переключатель
 */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  var NATIVE = !!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform());
  var PWA = !NATIVE && window.ItcPwa === true; // установленное PWA (standalone) — флаг ставит pwa-standalone.js только в сборке pwa
  if (!NATIVE && !PWA) return;
  var P = (NATIVE && Cap.Plugins) || {};
  (function () { if (document.querySelector('link[href="/css/native-features.css"]')) return; var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/css/native-features.css'; document.head.appendChild(l); })();
  var LS = window.localStorage;
  var DEMO = !!window.DemoBackend || !window.AppServer;
  var FOLLOW_KEY = 'itc.follows', MODE_KEY = 'itc.myMode', CACHE = 'itc.cache:', SETTINGS = 'itc.notify';

  function jget(k, d) { try { var v = JSON.parse(LS.getItem(k)); return v == null ? d : v; } catch (e) { return d; } }
  function jset(k, v) { try { LS.setItem(k, JSON.stringify(v)); } catch (e) { pruneCache(); try { LS.setItem(k, JSON.stringify(v)); } catch (e2) { /* полон */ } } }

  // ---------- «Мои кружки» ----------
  var Follows = {
    all: function () { return jget(FOLLOW_KEY, []).filter(function (x) { return Number.isInteger(x) && x > 0; }); },
    has: function (id) { return Follows.all().indexOf(id) >= 0; },
    toggle: function (id) {
      var a = Follows.all(), i = a.indexOf(id);
      if (i >= 0) a.splice(i, 1); else a.push(id);
      jset(FOLLOW_KEY, a);
      document.dispatchEvent(new CustomEvent('itc:follows', { detail: a }));
      configureNative().then(syncNow);
      return i < 0;
    }
  };
  var myMode = function () { return LS.getItem(MODE_KEY) === '1'; };

  // ---------- fetch: офлайн-кэш + фильтр «Мои» ----------
  var baseFetch = window.fetch.bind(window);
  var offline = false;
  function apiPath(input) {
    try { var u = new URL(typeof input === 'string' ? input : input.url, location.href); return u.pathname.indexOf('/api/') === 0 ? u.pathname + u.search : null; }
    catch (e) { return null; }
  }
  function pruneCache() {
    var keys = [];
    for (var i = 0; i < LS.length; i++) { var k = LS.key(i); if (k && k.indexOf(CACHE) === 0) keys.push(k); }
    keys.map(function (k) { return [k, (jget(k, {}).t || 0)]; }).sort(function (a, b) { return a[1] - b[1]; })
      .slice(0, Math.ceil(keys.length / 2)).forEach(function (x) { LS.removeItem(x[0]); });
  }
  function setOffline(v) {
    if (offline === v) return;
    offline = v;
    document.documentElement.classList.toggle('itc-offline', v);
    banner();
  }
  function jsonResponse(body, extra) {
    return new Response(JSON.stringify(body), { status: 200, headers: Object.assign({ 'Content-Type': 'application/json' }, extra || {}) });
  }
  function filterMine(path, body) {
    if (!myMode() || path.indexOf('/api/schedule?') !== 0 || !Array.isArray(body)) return body;
    var f = Follows.all();
    return body.filter(function (e) { return f.indexOf(e.club_id) >= 0; });
  }
  window.fetch = function (input, init) {
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var path = apiPath(input);
    var unfiltered = init && init.itcUnfilteredSchedule;
    if (path && method !== 'GET' && path.indexOf('/api/admin') === 0) {
      // правка в админке → кэш публичных данных устарел (иначе каталог/расписание показали бы старое до TTL)
      return baseFetch(input, init).then(function (r) { if (r.ok) dropCaches(); return r; });
    }
    // Cache only public resources. Admin/push responses are private,
    // including when the same device changes accounts while offline.
    if (path && init && init.itcPersistentWeekCache && /^\/api\/schedule(\?|$)/.test(path)) return baseFetch(input, init);
    if (!path || method !== 'GET' || !/^\/api\/(schedule|clubs|categories|leaders|rooms)(\/|\?|$)/.test(path)) return baseFetch(input, init);
    return baseFetch(input, init).then(function (r) {
      setOffline(navigator.onLine === false); // в PWA ответ без сети может прийти из кэша service worker
      if (!r.ok || !/json/.test(r.headers.get('content-type') || '')) return r;
      return r.clone().json().then(function (body) {
        var stamp = r.headers.get('X-Clubs-Cached-At') || new Date().toISOString();
        jset(CACHE + path, { t: Date.parse(stamp), b: body });
        var events = unfiltered ? body : filterMine(path, body);
        return events === body ? r : jsonResponse(events, {
          'X-Clubs-Cached-At': stamp, 'X-Clubs-Offline': r.headers.get('X-Clubs-Offline') || '0' });
      }, function () { return r; });
    }, function (err) {
      if (err && err.name === 'AbortError') throw err;
      var hit = jget(CACHE + path, null);
      if (!hit || Date.now() - hit.t > 48 * 3600e3) { setOffline(true); throw err; }
      setOffline(true);
      return jsonResponse(unfiltered ? hit.b : filterMine(path, hit.b), { 'X-ITC-Cached': String(hit.t),
        'X-Clubs-Offline': '1', 'X-Clubs-Cached-At': new Date(hit.t).toISOString() });
    });
  };
  // Remove private entries written by earlier app versions.
  var privateKeys = [];
  for (var ci = 0; ci < LS.length; ci++) {
    var ck = LS.key(ci);
    if (ck && ck.indexOf(CACHE) === 0 && !/^\/api\/(schedule|clubs|categories|leaders|rooms)(\/|\?|$)/.test(ck.slice(CACHE.length))) privateKeys.push(ck);
  }
  privateKeys.forEach(function (key) { LS.removeItem(key); });
  function dropCaches() {
    var keys = [];
    for (var i = 0; i < LS.length; i++) { var k = LS.key(i); if (k && (k.indexOf(CACHE) === 0 || k.indexOf('itc.sched.') === 0)) keys.push(k); }
    keys.forEach(function (k) { LS.removeItem(k); });
    window.dispatchEvent(new CustomEvent('public:cache-invalidated'));
  }
  window.addEventListener('online', function () { setOffline(false); syncNow(); });
  window.addEventListener('offline', function () { setOffline(true); });
  if (navigator.onLine === false) offline = true, document.documentElement.classList.add('itc-offline');

  // ---------- нативный плагин ----------
  function N() { return P.ItcNative; }
  function settings() {
    var saved = jget(SETTINGS, {}), changes = saved.notifyChanges !== false;
    return Object.assign({ reminderMinutes: 15, notifyCancellations: changes, notifyMoves: changes, notifyAnnouncements: true }, saved);
  }
  function configureNative() {
    if (!N()) return Promise.resolve(null);
    var s = settings();
    return N().configure({ follows: Follows.all(), server: DEMO ? '' : ((window.AppServer && window.AppServer.get()) || ''),
      demo: DEMO, reminderMinutes: s.reminderMinutes, notifyChanges: s.notifyCancellations || s.notifyMoves,
      notifyCancellations: s.notifyCancellations, notifyMoves: s.notifyMoves, notifyAnnouncements: s.notifyAnnouncements !== false }).catch(function () { return null; });
  }
  function mskMonday(offsetWeeks) {
    var d = new Date(Date.now() + 3 * 3600e3); // Москва UTC+3
    var wd = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - wd + 7 * offsetWeeks);
    return d.toISOString().slice(0, 10);
  }
  var syncing = null;
  function syncNow() {
    if (syncing) return syncing;
    syncing = Promise.all([0, 1].map(function (w) {
      return baseFetch('/api/schedule?week=' + mskMonday(w), { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    })).then(function (weeks) {
      var events = [].concat(weeks[0], weeks[1]);
      jset('itc.lastSync', Date.now());
      return N() ? N().sync({ events: events }) : null;
    }).catch(function () { return null; }).then(function (r) {
      if (N() && N().checkAnnouncements) N().checkAnnouncements().catch(function () {}); // объявления — отдельным запросом, сеть может быть и без расписания
      syncing = null; return r;
    });
    return syncing;
  }

  // ---------- UI ----------
  var STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/></svg>';
  var BELL = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4"/></svg>';
  function el(tag, attrs, html) { var e = document.createElement(tag); for (var k in attrs || {}) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e; }
  function toast(text) {
    if (window.ItcHuman) text = window.ItcHuman.clean(text) || 'Что-то пошло не так. Попробуйте ещё раз';
    var t = el('div', { class: 'itc-toast', role: 'status' }); t.textContent = text; document.body.appendChild(t);
    setTimeout(function () { t.classList.add('show'); }, 10);
    setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 300); }, 2200);
  }
  function banner() {
    var b = document.getElementById('itc-offline-banner');
    if (!offline) { if (b) b.remove(); return; }
    if (b || !document.body) return;
    b = el('div', { id: 'itc-offline-banner', role: 'status' });
    var t = jget('itc.lastSync', 0);
    b.textContent = 'Нет сети — показаны сохранённые данные' + (t ? ' (обновлено ' + new Date(t).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ')' : '');
    document.body.prepend(b);
  }
  function starButton(id, compact) {
    var b = el('button', { type: 'button', class: 'itc-follow' + (compact ? ' compact' : ''), 'data-club-id': String(id) });
    function paint() {
      var on = Follows.has(id);
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
      b.setAttribute('aria-label', on ? 'Убрать из «Моих кружков»' : 'Добавить в «Мои кружки»');
      b.innerHTML = STAR + (compact ? '' : '<span>' + (on ? 'В «Моих кружках»' : 'В «Мои кружки»') + '</span>');
    }
    paint();
    b.addEventListener('click', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      var on = Follows.toggle(id);
      toast(on ? (PWA ? 'Добавлено в «Мои кружки»' : 'Добавлено в «Мои кружки». Напомним о занятиях') : 'Убрано из «Моих кружков»');
      if (on && N()) N().requestNotifications().catch(function () {});
    });
    document.addEventListener('itc:follows', paint);
    return b;
  }

  function pageClub() {
    var id = parseInt(new URLSearchParams(location.search).get('id'), 10);
    var h = document.getElementById('club-name');
    if (!id || !h || document.querySelector('.itc-follow')) return;
    h.insertAdjacentElement('afterend', starButton(id, false));
  }
  function pageClubs() {
    function decorate() {
      document.querySelectorAll('a.club-card').forEach(function (a) {
        if (a.querySelector('.itc-follow')) return;
        var m = /[?&]id=(\d+)/.exec(a.getAttribute('href') || '');
        if (!m) return;
        a.classList.add('itc-has-follow');
        a.appendChild(starButton(parseInt(m[1], 10), true));
      });
    }
    decorate();
    new MutationObserver(decorate).observe(document.body, { childList: true, subtree: true });
  }
  function pageSchedule() {
    var row = document.getElementById('schedule-actions');
    var header = document.querySelector('.schedule-page > .campus-header');
    if (!row || !header || document.getElementById('itc-my-toggle')) return;
    var q = new URLSearchParams(location.search);
    if (q.get('my') === '1') LS.setItem(MODE_KEY, '1');
    var s = el('button', { type: 'button', id: 'itc-notify-open', class: 'settings-button',
      'aria-label': 'Уведомления', 'aria-haspopup': 'dialog' }, BELL);
    s.addEventListener('click', openSheet);
    var t = el('button', { type: 'button', id: 'itc-my-toggle', class: 'glass-action' });
    function paint() {
      var n = Follows.all().length;
      t.setAttribute('aria-pressed', String(myMode()));
      t.innerHTML = STAR + '<span>Мои кружки</span>' + (n ? '<span class="my-follow-count">· ' + n + '</span>' : '');
    }
    function toggleMine() {
      if (!Follows.all().length && !myMode()) { toast('Отметьте кружки звёздочкой ☆ в каталоге'); paint(); return; }
      LS.setItem(MODE_KEY, myMode() ? '0' : '1'); paint(); reload(); document.dispatchEvent(new CustomEvent('itc:mymode'));
    }
    t.addEventListener('click', toggleMine);
    row.insertBefore(t, document.getElementById('toggle-filters'));
    header.insertBefore(s, header.querySelector('.app-gear, [data-settings-button]'));
    document.addEventListener('itc:follows', function () { paint(); if (myMode()) reload(); });
    paint();
    if (myMode()) reload();
  }
  function reload() {
    var c = document.getElementById('category');
    if (c) c.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ---------- шторка «Напоминания и виджеты» ----------
  function openSheet() {
    if (PWA) { if (window.ItcPwaFeatures) window.ItcPwaFeatures.openSheet(); return; }
    if (document.getElementById('itc-sheet')) return;
    var s = settings(), opener = document.activeElement;
    var wrap = el('div', { id: 'itc-sheet', class: 'itc-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'itc-sheet-title' });
    wrap.innerHTML = '<div class="itc-sheet-card">' +
      '<h2 id="itc-sheet-title">Уведомления</h2>' +
      '<p class="itc-muted">Отмены и переносы приходят по «Моим кружкам». Напоминания работают с сохранённым расписанием.</p>' +
      '<label class="itc-row"><span>Напоминать до начала</span><select id="itc-remind">' +
      [['0', 'Не напоминать'], ['15', 'За 15 минут'], ['30', 'За 30 минут'], ['60', 'За 1 час'], ['120', 'За 2 часа']].map(function (o) {
        return '<option value="' + o[0] + '"' + (String(s.reminderMinutes) === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') +
      '</select></label>' +
      '<label class="itc-row"><span>Отмены занятий</span><input type="checkbox" id="itc-cancellations"' + (s.notifyCancellations ? ' checked' : '') + '></label>' +
      '<label class="itc-row"><span>Переносы занятий</span><input type="checkbox" id="itc-moves"' + (s.notifyMoves ? ' checked' : '') + '></label>' +
      '<label class="itc-row"><span>Объявления от администрации</span><input type="checkbox" id="itc-ann"' + (s.notifyAnnouncements !== false ? ' checked' : '') + '></label>' +
      '<p id="itc-perm" class="itc-warn" hidden>Уведомления запрещены в настройках. <button type="button" class="text-button" id="itc-perm-open">Открыть настройки</button></p>' +
      '<div id="itc-channel-settings" hidden><h3>Звук и вибрация</h3>' +
      '<p class="itc-muted small">Каждая кнопка открывает настройки своей категории в Android.</p>' +
      '<div class="itc-actions"><button type="button" data-channel="cancelled">Отмены занятий</button><button type="button" data-channel="moved">Переносы занятий</button></div></div>' +
      '<h3>Виджеты на рабочий стол</h3>' +
      '<div class="itc-actions"><button type="button" data-pin="next">Следующее занятие</button><button type="button" data-pin="today">Сегодня (4×2)</button></div>' +
      '<p class="itc-muted small">Если кнопка не сработала: долгое нажатие на рабочем столе → Виджеты → «KipClub».</p>' +
      '<button type="button" class="itc-close">Готово</button></div>';
    document.body.appendChild(wrap);
    function save() {
      jset(SETTINGS, { reminderMinutes: parseInt(wrap.querySelector('#itc-remind').value, 10),
        notifyCancellations: wrap.querySelector('#itc-cancellations').checked, notifyMoves: wrap.querySelector('#itc-moves').checked,
        notifyAnnouncements: wrap.querySelector('#itc-ann').checked });
      configureNative().then(checkPerm);
    }
    function checkPerm(st) {
      wrap.querySelector('#itc-perm').hidden = !st || st.notificationsAllowed !== false;
      wrap.querySelector('#itc-channel-settings').hidden = !st || !st.changeChannels;
    }
    wrap.querySelectorAll('input, select').forEach(function (field) {
      field.addEventListener('change', function () {
        save();
        if (N() && (field.checked || Number(field.value) > 0)) N().requestNotifications().then(checkPerm, function () {});
      });
    });
    wrap.querySelector('#itc-perm-open').addEventListener('click', function () { if (N()) N().openNotificationSettings(); });
    wrap.querySelectorAll('[data-channel]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (N()) N().openNotificationSettings({ kind: b.dataset.channel }).catch(function () { toast('Откройте настройки уведомлений в Android'); });
      });
    });
    wrap.querySelectorAll('[data-pin]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (!N()) return;
        N().pinWidget({ kind: b.getAttribute('data-pin') }).then(function (r) { if (!r || !r.requested) toast('Лаунчер не поддерживает добавление из приложения — добавьте виджет вручную'); });
      });
    });
    function close() { wrap.remove(); if (opener && opener.isConnected) opener.focus({ preventScroll: true }); }
    wrap.itcClose = close;
    wrap.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    wrap.querySelector('.itc-close').focus({ preventScroll: true });
    wrap.querySelector('.itc-close').addEventListener('click', close);
    wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
    if (N()) N().getState().then(checkPerm, function () {});
  }

  // ---------- ссылки itckruzhki://open/... (ярлыки, уведомления, виджеты) ----------
  function routeOf(url) {
    var m = /^itckruzhki:\/\/open(\/[^?#]*)?(\?[^#]*)?/.exec(url || '');
    if (!m) return null;
    var p = m[1] || '/', q = m[2] || '';
    var map = { '/': '/index.html', '/my': '/index.html?my=1', '/clubs': '/clubs.html', '/club': '/club.html' + q, '/today': '/index.html?from=shortcut' };
    return map[p] || '/index.html';
  }
  function go(url) {
    var r = routeOf(url);
    if (r && r !== location.pathname + location.search) location.href = r;
  }
  if (P.App) {
    if (P.App.addListener) P.App.addListener('appUrlOpen', function (e) { go(e && e.url); });
    if (P.App.getLaunchUrl && !sessionStorage.getItem('itc.launchHandled')) {
      sessionStorage.setItem('itc.launchHandled', '1');
      P.App.getLaunchUrl().then(function (r) { if (r && r.url) go(r.url); }, function () {});
    }
    if (P.App.addListener) P.App.addListener('appStateChange', function (st) { if (st && st.isActive) syncNow(); });
  }

  window.ItcFeatures = { Follows: Follows, syncNow: syncNow, routeOf: routeOf, openSheet: openSheet, baseFetch: baseFetch,
    isMyMode: myMode, toast: toast, el: el, host: NATIVE ? 'native' : 'pwa' };
  if (PWA) document.addEventListener('visibilitychange', function () { if (!document.hidden) syncNow(); });

  function boot() {
    var p = location.pathname;
    if (/\/club\.html$/.test(p)) { pageClub(); new MutationObserver(pageClub).observe(document.body, { childList: true, subtree: true }); }
    if (/\/clubs\.html$/.test(p)) pageClubs();
    if (p === '/' || /\/index\.html$/.test(p)) pageSchedule();
    banner();
    if (!sessionStorage.getItem('itc.synced')) { sessionStorage.setItem('itc.synced', '1'); var idle = window.requestIdleCallback || function (fn) { setTimeout(fn, 800); }; idle(function () { configureNative().then(syncNow); }, { timeout: 2500 }); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
