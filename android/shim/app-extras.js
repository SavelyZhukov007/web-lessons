/* APK: сохранение файлов (ItcFiles), журнал (ItcLog, «Логи» в настройках), pull-to-refresh, быстрые отмена/перенос (только админ),
 * подключение к тестовому серверу из демо (поиск в сети, «Вернуться к демо-данным»). */
(function () {
  'use strict';
  var P = (window.Capacitor && window.Capacitor.Plugins) || {}, LS = window.localStorage;
  function toast(t) { if (window.ItcFeatures) window.ItcFeatures.toast(t); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  // ---------- файлы: Filesystem (кэш) + «Поделиться» ----------
  window.ItcFiles = {
    save: function (blob, name, title) {
      if (!(P.Filesystem && P.Share)) { var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000); return Promise.resolve(); }
      return new Promise(function (ok, fail) { var r = new FileReader(); r.onload = function () { ok(String(r.result).split(',')[1]); }; r.onerror = fail; r.readAsDataURL(blob); })
        .then(function (data) { return P.Filesystem.writeFile({ path: name, data: data, directory: 'CACHE' }); })
        .then(function (w) { return P.Share.share({ title: title || name, files: [w.uri], dialogTitle: 'Сохранить или отправить' }); })
        .catch(function (e) { if (!/cancel/i.test(String(e && e.message))) throw e; });
    },
  };

  // ---------- журнал ----------
  var LOGK = 'itc.log', MAX = 400, KEEP = 21 * 864e5;
  function logs() { try { return (JSON.parse(LS.getItem(LOGK)) || []).filter(function (x) { return Date.now() - x.t < KEEP; }); } catch (e) { return []; } }
  var buf = logs(), dirty = 0;
  function push(level, msg) {
    buf.push({ t: Date.now(), l: level, m: String(msg).slice(0, 500), p: location.pathname }); if (buf.length > MAX) buf.splice(0, buf.length - MAX);
    if (!dirty) dirty = setTimeout(function () { dirty = 0; try { LS.setItem(LOGK, JSON.stringify(buf)); } catch (e) { buf.splice(0, buf.length / 2); } }, 500);
  }
  ['error', 'warn'].forEach(function (k) { var o = console[k]; console[k] = function () { try { push(k, Array.prototype.map.call(arguments, function (a) { return a && a.stack ? a.stack : typeof a === 'object' ? JSON.stringify(a) : a; }).join(' ')); } catch (e) { /* */ } return o.apply(console, arguments); }; });
  window.addEventListener('error', function (e) { push('error', (e.message || 'error') + ' @' + (e.filename || '') + ':' + (e.lineno || '')); });
  window.addEventListener('unhandledrejection', function (e) { push('error', 'unhandled: ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)); });
  var ver = (window.ItcSplash && window.ItcSplash.version) || '';
  push('info', 'start ' + ver + ' ' + navigator.userAgent.slice(0, 120));
  window.ItcLog = {
    info: function (m) { push('info', m); }, all: function () { return buf.slice(); },
    text: function () { return buf.map(function (x) { return new Date(x.t).toISOString() + ' ' + x.l.toUpperCase() + ' ' + x.p + ' ' + x.m; }).join('\n'); },
    clear: function () { buf = []; LS.removeItem(LOGK); },
  };

  // ---------- pull-to-refresh (расписание, каталог, кружок) ----------
  function ptr() {
    if (/^\/admin\//.test(location.pathname) || /qr\.html$/.test(location.pathname)) return;
    var ind = document.createElement('div'); ind.className = 'itc-ptr'; ind.innerHTML = '<i></i>'; ind.setAttribute('aria-hidden', 'true'); document.body.appendChild(ind);
    var y0 = null, d = 0, busy = false, TH = 72;
    document.addEventListener('touchstart', function (e) {
      if (busy || window.scrollY > 0 || document.documentElement.classList.contains('itc-ob-open') || e.touches.length !== 1 || e.target.closest('dialog, .itc-sheet, input, select, textarea')) { y0 = null; return; }
      y0 = e.touches[0].clientY; d = 0;
    }, { passive: true });
    document.addEventListener('touchmove', function (e) {
      if (y0 == null) return; d = Math.max(0, e.touches[0].clientY - y0); if (window.scrollY > 0) { y0 = null; d = 0; }
      var k = Math.min(1, d / TH); ind.style.transform = 'translateY(' + (Math.min(d, TH * 1.4) * .6 - 60 + 20 * k) + 'px) rotate(' + (k * 270) + 'deg)'; ind.style.opacity = String(k);
    }, { passive: true });
    document.addEventListener('touchend', function () {
      if (y0 == null) return; y0 = null;
      if (d < TH) { ind.style.transform = ''; ind.style.opacity = ''; return; }
      busy = true; ind.classList.add('spin'); ind.style.transform = 'translateY(24px)'; ind.style.opacity = '1';
      if (window.ItcHaptics) window.ItcHaptics.tap();
      var finish = function () { busy = false; ind.classList.remove('spin'); ind.style.transform = ''; ind.style.opacity = ''; };
      var handled = false;
      document.dispatchEvent(new CustomEvent('itc:refresh', { detail: { done: function (p) { handled = true; Promise.resolve(p).then(finish, finish); } } }));
      if (window.ItcFeatures && window.ItcFeatures.syncNow) window.ItcFeatures.syncNow();
      if (!handled) setTimeout(function () { location.reload(); }, 250);
    });
  }

  // ---------- быстрые отмена/перенос: только при входе администратора ----------
  function adminToken() { try { return LS.getItem('clubs.adminToken') || LS.getItem('adminToken') || ''; } catch (e) { return ''; } }
  function quick() {
    if (!/^\/(index\.html)?$/.test(location.pathname)) return;
    var timer = 0;
    document.addEventListener('contextmenu', function (e) { if (e.target.closest && e.target.closest('.calendar-event') && window.ItcQuickAdmin) e.preventDefault(); });
    document.addEventListener('pointerdown', function (e) {
      var c = e.target.closest && e.target.closest('.calendar-event'); if (!c || !window.ItcQuickAdmin || !window.ItcQuickAdmin()) return;
      timer = setTimeout(function () { timer = 0; if (window.ItcHaptics) window.ItcHaptics.tap(); window.ItcQuickSheet && window.ItcQuickSheet(c); }, 550);
    });
    ['pointerup', 'pointercancel', 'pointermove'].forEach(function (t) { document.addEventListener(t, function (e) { if (t === 'pointermove' && Math.abs(e.movementY || 0) < 3) return; clearTimeout(timer); }); });
  }

  // ---------- быстрая отмена/перенос (только для вошедшего администратора) ----------
  window.ItcQuickAdmin = function () { return !!adminToken(); };
  window.ItcQuickSheet = function (card) {
    var id = card.dataset.eventId, ev = window.ItcEvent && window.ItcEvent(id); if (!ev) return;
    var sid = +String(id).split(':')[0], date = String(id).split(':')[1] || ev.date;
    var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
    var w = sheet('<h2>' + esc(ev.club_name || 'Занятие') + '</h2><p class="itc-muted small">' + esc(date) + ' · ' + esc(ev.start_time) + '–' + esc(ev.end_time) + ' · ' + esc(ev.room_name || '') + '</p>' +
      '<label class="itc-field">Комментарий для студентов<input data-c maxlength="300" placeholder="Например: преподаватель болеет"></label>' +
      '<button type="button" class="btn btn--danger itc-wide" data-cancel>Отменить занятие</button>' +
      '<h3>Перенести</h3><div class="itc-row3"><input type="date" data-d value="' + esc(date) + '"><input type="time" data-s value="' + esc(String(ev.start_time).slice(0, 5)) + '"><input type="time" data-e value="' + esc(String(ev.end_time).slice(0, 5)) + '"></div>' +
      '<button type="button" class="btn btn--tonal itc-wide" data-move>Перенести</button><p class="itc-muted small" data-msg role="status"></p>');
    var q = function (s) { return w.querySelector(s); };
    function send(path, body) {
      q('[data-msg]').textContent = 'Сохраняем…';
      return fetch('/api/admin/exceptions/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + adminToken() }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(window.ItcHuman ? window.ItcHuman.error(r.status, j.detail) : 'Не удалось выполнить действие'); }); })
        .then(function () { if (window.ItcHaptics) window.ItcHaptics.success && window.ItcHaptics.success(); w.remove(); document.dispatchEvent(new CustomEvent('itc:refresh', { detail: {} })); })
        .catch(function (e) { q('[data-msg]').textContent = typeof e.message === 'string' ? e.message : 'Не удалось сохранить'; window.ItcLog && window.ItcLog.info('quick ' + path + ' ' + e.message); });
    }
    q('[data-cancel]').addEventListener('click', function () { if (confirm('Отменить занятие ' + date + '?')) send('cancellations', { session_id: sid, original_date: date, comment: q('[data-c]').value.trim() }); });
    q('[data-move]').addEventListener('click', function () { send('moves', { session_id: sid, original_date: date, new_date: q('[data-d]').value, new_start_time: q('[data-s]').value, new_end_time: q('[data-e]').value, new_room_id: ev.room_id, comment: q('[data-c]').value.trim() }); });
  };

  // ---------- настройки: «Логи», «Тестовый сервер» ----------
  function sheet(html) {
    var w = document.createElement('div'); w.className = 'itc-sheet'; w.setAttribute('role', 'dialog'); w.setAttribute('aria-modal', 'true');
    w.innerHTML = '<div class="itc-sheet-card">' + html + '<button type="button" class="itc-close">Закрыть</button></div>'; document.body.appendChild(w);
    w.addEventListener('click', function (e) { if (e.target === w || e.target.closest('.itc-close')) w.remove(); }); return w;
  }
  function openLogs() {
    var w = sheet('<h2>Журнал приложения</h2><p class="itc-muted small">Ошибки и предупреждения за 21 день (не больше ' + MAX + ' строк). Хранится только на телефоне.</p>' +
      '<pre class="itc-log">' + esc(window.ItcLog.text().split('\n').slice(-150).join('\n') || 'Пусто') + '</pre>' +
      '<div class="itc-actions"><button type="button" data-share>Поделиться</button><button type="button" data-clear>Очистить</button></div>');
    w.querySelector('[data-share]').addEventListener('click', function () { window.ItcFiles.save(new Blob([window.ItcLog.text()], { type: 'text/plain' }), 'itc-log.txt', 'Журнал «KipClub»'); });
    w.querySelector('[data-clear]').addEventListener('click', function () { window.ItcLog.clear(); w.querySelector('pre').textContent = 'Пусто'; });
  }
  var T = window.ItcServerTools;
  function openServer() {
    var cur = ''; try { cur = LS.getItem('clubs.serverUrl') || ''; } catch (e) { /* */ }
    var w = sheet('<h2>Тестовый сервер</h2><p class="itc-muted small">Подключите приложение к своему серверу (FastAPI, та же сеть Wi-Fi). Демо-данные останутся на телефоне.</p>' +
      '<label class="itc-row"><span>Адрес</span><input data-url inputmode="url" autocapitalize="off" spellcheck="false" placeholder="192.168.1.50:8000" value="' + esc(cur) + '"></label>' +
      '<div class="itc-actions"><button type="button" data-find>Найти в сети</button><button type="button" data-test>Проверить</button><button type="button" data-use>Подключиться</button></div>' +
      '<ul class="itc-found" data-found></ul><p data-st role="status" class="itc-muted small"></p>' +
      (cur ? '<button type="button" data-demo class="text-button">Вернуться к демо-данным</button>' : ''));
    var inp = w.querySelector('[data-url]'), st = w.querySelector('[data-st]'), found = w.querySelector('[data-found]');
    function test() {
      if (!T) { st.textContent = 'Недоступно в этой сборке'; return Promise.resolve(null); }
      var u = T.normalize(inp.value); if (!u) { st.textContent = 'Адрес не распознан'; return Promise.resolve(null); }
      st.textContent = 'Проверяем ' + u + '…';
      return T.info(u, 3000).then(function (i) { st.textContent = '✓ ' + (i.name || 'Сервер') + ' · API ' + i.api_version + (i.warning ? ' · ' + i.warning : ''); return u; },
        function (e) { st.textContent = '✗ ' + (e && e.message || 'Нет ответа'); return null; });
    }
    w.querySelector('[data-test]').addEventListener('click', test);
    w.querySelector('[data-use]').addEventListener('click', function () { test().then(function (u) { if (!u) return; LS.setItem('clubs.serverUrl', u); window.ItcLog.info('server ' + u); location.replace('/index.html'); }); });
    w.querySelector('[data-find]').addEventListener('click', function () {
      found.innerHTML = ''; st.textContent = 'Ищем серверы в сети (mDNS и подсеть /24)…';
      var D = P.ItcDiscovery;
      if (!D || !T) { st.textContent = 'Поиск доступен только в приложении на Android'; return; }
      discover(D, function (n) { st.textContent = 'Ищем… проверено адресов: ' + n; }).then(function (list) {
        st.textContent = list.length ? 'Найдено: ' + list.length : 'Ничего не найдено. Введите адрес вручную.';
        list.forEach(function (s) { var li = document.createElement('li'); var b = document.createElement('button'); b.type = 'button'; b.textContent = (s.name || 'Сервер') + ' — ' + s.url;
          b.addEventListener('click', function () { inp.value = s.url; test(); }); li.appendChild(b); found.appendChild(li); });
      }, function (e) { st.textContent = 'Поиск не удался: ' + (e && e.message || e); });
    });
    var demo = w.querySelector('[data-demo]');
    if (demo) demo.addEventListener('click', function () { LS.removeItem('clubs.serverUrl'); location.replace('/index.html'); });
  }
  // поиск: mDNS (_itc-kruzhki._tcp) + перебор /24 текущей Wi-Fi-сети на порту 8000 (GET /api/app/info, 24 параллельно)
  function discover(D, progress) {
    var out = {}, add = function (url, name) { out[url] = out[url] || { url: url, name: name }; };
    function probe(url) {
      return D.probe({ url: url + '/api/app/info', timeoutMs: 700 }).then(function (r) {
        try { var j = JSON.parse(r.body || '{}'); if (j.app === 'itc-kruzhki') add(url, j.name); } catch (e) { /* не сервер */ }
      }, function () {});
    }
    var nsd = D.nsd({ timeoutMs: 3000 }).then(function (r) { return Promise.all(((r && r.services) || []).map(function (s) { return probe('http://' + s.host + ':' + s.port); })); }, function () {});
    var scan = D.wifi().then(function (w) {
      if (!w || !w.lan || !w.ip) return;
      var base = w.ip.split('.').slice(0, 3).join('.'), ips = [], done = 0;
      for (var i = 1; i < 255; i++) if (base + '.' + i !== w.ip) ips.push('http://' + base + '.' + i + ':8000');
      function worker() { var u = ips.shift(); if (!u) return Promise.resolve(); return probe(u).then(function () { done++; if (done % 24 === 0) progress(done); return worker(); }); }
      var ws = []; for (var k = 0; k < 24; k++) ws.push(worker()); return Promise.all(ws);
    });
    return Promise.all([nsd, scan]).then(function () { return Object.keys(out).map(function (k) { return out[k]; }); });
  }
  function badge() {
    var u = ''; try { u = LS.getItem('clubs.serverUrl') || ''; } catch (e) { /* */ }
    if (!u || !window.APP_DEMO_BUILD) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'itc-server-badge'; b.textContent = 'Тестовый сервер · ' + u.replace(/^https?:\/\//, '');
    b.addEventListener('click', openServer); document.body.appendChild(b);
  }
  if (window.ItcSettingsExt && window.ITC_CHANNEL !== 'p') window.ItcSettingsExt.add(function (box, ui) {
    if (!box) return; // раздел «Для разработчиков» в Настройках (только каналы l/i)
    box.insertAdjacentHTML('beforeend', ui.row('Логи', { act: 'dev-logs' }) + (window.APP_DEMO_BUILD ? ui.row('Тестовый сервер', { act: 'dev-srv' }) : '') +
      (window.DemoBackend && window.DemoBackend.reset ? ui.row('Сбросить демо-данные', { act: 'dev-reset' }) : ''));
    box.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act^="dev-"]'); if (!b) return; e.stopPropagation(); ui.close();
      var a = b.getAttribute('data-act');
      if (a === 'dev-logs') openLogs(); else if (a === 'dev-srv') openServer();
      else if (confirm('Сбросить демо-данные? Расписание будет сгенерировано заново.')) { window.DemoBackend.reset(); location.reload(); }
    });
  });
  window.ItcConnect = { open: openServer, logs: openLogs };

  var PUB = window.ITC_CHANNEL === 'p'; // публичный канал: без тестового сервера, логов и прочих инструментов разработчика
  function boot() { ptr(); quick(); if (!PUB) badge(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
