/* Роли в APK: только «гость» (смотрит расписание, получает уведомления) и «администратор» (вход в админку).
 * Посещаемость по QR и профиль студента удалены: при первом запуске новой версии старые роли student/teacher
 * превращаются в гостя, а локальные данные отметок (зашифрованный профиль, очередь отметок) стираются. */
(function () {
  'use strict';
  var LS = window.localStorage, P = (window.Capacitor && window.Capacitor.Plugins) || {};
  var ROLE_KEY = 'itc.role';
  // ---------- хаптика (настройка «Вибрация») ----------
  var Haptics = {
    on: function () { return LS.getItem('itc.haptics') !== '0'; },
    set: function (v) { LS.setItem('itc.haptics', v ? '1' : '0'); },
    tap: function () { Haptics._do('light', 12); }, success: function () { Haptics._do('success', [18, 40, 18]); }, error: function () { Haptics._do('error', [40, 60, 40]); },
    _do: function (kind, pattern) {
      if (!Haptics.on()) return;
      var H = P.Haptics;
      try {
        if (H && kind === 'light') return void H.impact({ style: 'LIGHT' }).catch(function () {});
        if (H) return void H.notification({ type: kind === 'success' ? 'SUCCESS' : 'ERROR' }).catch(function () {});
        if (navigator.vibrate) navigator.vibrate(pattern);
      } catch (e) { /* нет вибромотора */ }
    },
  };
  window.ItcHaptics = Haptics;

  // ---------- утилиты ----------
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function el(html) { var d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function toast(t) { if (window.ItcFeatures && window.ItcFeatures.toast) window.ItcFeatures.toast(clean(t) || HUMAN[0]); }

  // ---------- t99: понятные ошибки — что случилось и что делать; без кодов, undefined и JSON ----------
  var HUMAN = {
    0: 'Нет связи с сервером. Проверьте интернет и попробуйте ещё раз',
    400: 'Запрос не принят. Проверьте введённые данные', 401: 'Сеанс истёк — войдите снова', 403: 'Недостаточно прав для этого действия',
    404: 'Не найдено — возможно, запись уже удалили. Обновите экран', 409: 'Конфликт с уже сохранёнными данными. Обновите экран и повторите',
    413: 'Слишком большой файл', 422: 'Проверьте заполнение полей', 429: 'Слишком много попыток. Подождите минуту и повторите',
    500: 'Ошибка на сервере. Попробуйте позже — если повторится, сообщите администратору', 502: 'Сервер временно недоступен. Попробуйте через минуту',
    503: 'Сервер временно недоступен. Попробуйте через минуту', 504: 'Сервер не ответил вовремя. Попробуйте ещё раз'
  };
  function clean(t) { t = String(t == null ? '' : t).trim(); return !t || /undefined|null|NaN|\[object|^[{\[]|Traceback|Error:|fetch|NetworkError|Load failed|\b[A-Z_]{5,}\b/.test(t) ? '' : t; }
  function humanError(status, detail) {
    var d = detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail.message || detail.detail) : detail;
    if (Array.isArray(d)) d = d.map(function (x) { return x && x.msg; }).filter(Boolean)[0] ? 'Проверьте заполнение полей' : '';
    var c = detail && typeof detail === 'object' && Array.isArray(detail.conflicts) && detail.conflicts[0];
    if (c && c.club_name) { // пересечение: называем, с чем именно
      var dd = c.date ? String(c.date).split('-').reverse().slice(0, 2).join('.') + ', ' : '';
      return 'Пересекается с «' + clean(c.club_name) + '»: ' + dd + c.start_time + '–' + c.end_time + (c.room_name ? ', ' + clean(c.room_name) : '') + (c.leader_name ? ', ' + clean(c.leader_name) : '') + '. Выберите другое время или аудиторию.';
    }
    return clean(d) || HUMAN[status] || (status >= 500 ? HUMAN[500] : status >= 400 ? HUMAN[400] : HUMAN[0]);
  }
  window.ItcHuman = { error: humanError, clean: clean };

  // ---------- единая сессия {role: guest|admin, name, exp} ----------
  // Админ: токены выдаёт и хранит админка сайта (clubs.adminToken / clubs.adminRefresh); роль ставится по успешному
  // POST /api/admin/login и снимается по /api/admin/logout или 401 при обновлении. Срок — по refresh_expires_in.
  var SES_KEY = 'itc.session', ROLES = { guest: 'Гость', admin: 'Сотрудник' };
  // Наследие удалённой посещаемости: профиль студента, очередь отметок, ключ шифрования в IndexedDB.
  function wipeAttendanceLeftovers() {
    ['itc.vault.v1', 'itc.checkinQueue', 'itc.studentName', 'itc.teacher.session'].forEach(function (k) { LS.removeItem(k); });
    try { if (window.indexedDB) indexedDB.deleteDatabase('itc-secure'); } catch (e) { /* нет IndexedDB */ }
  }
  var Session = {
    get: function () {
      var v = null; try { v = JSON.parse(LS.getItem(SES_KEY)); } catch (e) { /* битое */ }
      if (!v) { var old = LS.getItem(ROLE_KEY); if (!old) return null; v = { role: old }; } // миграция с itc.role
      if (v.role === 'teacher' || v.role === 'student') { // роли удалены — остаётся гость
        v = { role: 'guest' }; LS.setItem(SES_KEY, JSON.stringify(v)); LS.setItem(ROLE_KEY, 'guest'); wipeAttendanceLeftovers();
      }
      if (!ROLES[v.role]) return null;
      if (v.exp && v.exp < Date.now() && v.role === 'admin') { // истёк вход сотрудника
        LS.removeItem('clubs.adminToken'); LS.removeItem('clubs.adminRefresh');
        v = { role: 'guest', expired: v.role }; LS.setItem(SES_KEY, JSON.stringify(v)); LS.setItem(ROLE_KEY, 'guest');
      }
      return v;
    },
    role: function () { var v = Session.get(); return v ? v.role : ''; },
    label: function (r) { return ROLES[r] || ''; },
    set: function (role, name, ttl) {
      var v = { role: role, name: name || '', since: Date.now() }; if (ttl) v.exp = Date.now() + ttl;
      LS.setItem(SES_KEY, JSON.stringify(v)); LS.setItem(ROLE_KEY, role);
      try { window.dispatchEvent(new CustomEvent('itc:session', { detail: v })); } catch (e) { /* старый WebView */ }
      return v;
    },
    logout: async function () {
      if (Session.role() === 'admin') {
        try { await fetch('/api/admin/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + (LS.getItem('clubs.adminToken') || '') } }); } catch (e) { /* без сети — всё равно выходим локально */ }
        LS.removeItem('clubs.adminToken'); LS.removeItem('clubs.adminRefresh');
      }
      Session.set('guest');
    },
  };
  window.ItcSession = Session;
  if (LS.getItem('itc.vault.v1') || LS.getItem('itc.checkinQueue')) wipeAttendanceLeftovers(); // гость/админ со старыми данными

  // перехват входа/выхода админки сайта → роль admin/guest
  // перехват входа/выхода админки сайта → роль admin/guest
  if (window.fetch) {
    var _f = window.fetch;
    window.fetch = function (u, o) {
      var url = typeof u === 'string' ? u : (u && u.url) || '';
      var pr = _f.apply(this, arguments);
      if (/\/api\/admin\/(login|logout)(\?|$)/.test(url)) pr.then(function (r) {
        if (/logout/.test(url)) { Session.set('guest'); return; }
        if (r.ok) r.clone().json().then(function (j) { if (j && j.access_token) Session.set('admin', (j.admin && j.admin.login) || 'Администратор', ((j.refresh_expires_in || 2592000) * 1000)); }, function () {});
      }, function () {});
      return pr;
    };
  }

  // ---------- общий full-screen слой ----------
  function screen(html, cls) {
    var s = el('<section class="itc-ob ' + (cls || '') + '" role="dialog" aria-modal="true">' + html + '</section>');
    document.body.appendChild(s); document.documentElement.classList.add('itc-ob-open');
    requestAnimationFrame(function () { s.classList.add('in'); });
    s.close = function () { s.classList.remove('in'); s.classList.add('out'); document.documentElement.classList.remove('itc-ob-open'); setTimeout(function () { s.remove(); }, 260); };
    var f = s.querySelector('input'); if (f) setTimeout(function () { f.focus({ preventScroll: true }); }, 300);
    return s;
  }
  var ICON = '<span class="itc-ob-icon kc-icon" aria-hidden="true"></span>';

  function roleScreen() {
    var L = window.ITC_CHANNEL === 'l';
    var s = screen('<div class="itc-ob-card">' + ICON + '<h1>KipClub</h1><p class="itc-ob-lead">Расписание кружков колледжа, отмены и переносы. Вход для сотрудников можно выбрать и позже в Настройках.</p>' +
      '<button type="button" class="itc-ob-primary" data-role="guest">Смотреть расписание</button>' +
      '<button type="button" class="itc-ob-secondary" data-role="admin">Я сотрудник — войти в админку</button>' +
      (L ? '<button type="button" class="itc-ob-link" data-role="demo-admin">Демо: войти как администратор</button>' : '') + '</div>' +
      '<footer class="itc-ob-foot"><span>' + (window.ITC_VERSION || '') + '</span><span>Made by ИТС КИПФИН</span></footer>', 'itc-ob-role');
    s.addEventListener('click', async function (e) {
      var b = e.target.closest('[data-role]'); if (!b) return; Haptics.tap();
      var r = b.getAttribute('data-role');
      s.close();
      if (r === 'admin') location.href = '/admin/login.html';
      else if (r === 'demo-admin') location.href = '/admin/login.html?demo=1';
      else { if (Session.role() === 'admin') await Session.logout(); else Session.set('guest'); if (/^\/admin\//.test(location.pathname)) location.href = '/'; }
    });
  }
  window.ItcRoles = { roleScreen: roleScreen };

  // ---------- t99: экран «Настройки» (шестерёнка в шапке) — сгруппированный список ----------
  var CHEV = '<svg class="itc-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var exts = [];
  window.ItcSettingsExt = { add: function (fn) { exts.push(fn); } };
  function row(label, opt) {
    opt = opt || {};
    return '<button type="button" class="itc-row' + (opt.danger ? ' itc-row-danger' : '') + '" data-act="' + opt.act + '"><span class="itc-row-tx"><span>' + label + '</span>' +
      (opt.sub ? '<small>' + esc(opt.sub) + '</small>' : '') + '</span>' + (opt.value ? '<span class="itc-row-val">' + esc(opt.value) + '</span>' : '') + (opt.danger ? '' : CHEV) + '</button>';
  }
  function seg(name, items, cur) {
    return '<div class="itc-seg" role="radiogroup" data-seg="' + name + '">' + items.map(function (t) {
      return '<button type="button" role="radio" data-v="' + t[0] + '" aria-checked="' + (t[0] === cur) + '">' + t[1] + '</button>'; }).join('') + '</div>';
  }
  var ACC = [['brick', 'Кирпичный'], ['blue', 'Синий'], ['green', 'Зелёный'], ['violet', 'Фиолетовый']];
  function settingsScreen() {
    var T = window.ClubsTheme, pr = T ? T.get() : { theme: 'system', accent: 'brick', textSize: 'normal' };
    var ses = Session.get() || { role: 'guest' }, r = ses.role, DEV = window.ITC_CHANNEL && window.ITC_CHANNEL !== 'p';
    var acc;
    if (r === 'guest' || !r) acc = '<div class="itc-acc"><div class="itc-acc-ava" aria-hidden="true">?</div><div class="itc-acc-tx"><b>Гость</b><small>' +
      (ses.expired ? 'Срок входа истёк — войдите снова' : 'Расписание и уведомления доступны без входа') + '</small></div></div>' +
      '<button type="button" class="itc-ob-secondary itc-acc-btn" data-act="admin-login">Войти как сотрудник</button>';
    else acc = '<div class="itc-acc"><div class="itc-acc-ava" aria-hidden="true">' + esc((ses.name || ROLES[r]).trim().charAt(0).toUpperCase()) + '</div><div class="itc-acc-tx"><b>' + esc(ses.name || ROLES[r]) + '</b><small>' + ROLES[r] + '</small></div></div>' +
      row('Админка', { act: 'admin' }) + row('Выйти', { act: 'logout', danger: true });
    var s = screen('<div class="itc-set">' +
      '<header class="itc-set-head"><button type="button" class="itc-set-back" data-act="close" aria-label="Назад"><svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><h1>Настройки</h1></header>' +
      '<div class="itc-set-body">' +
      '<h2>Аккаунт</h2><div class="itc-group">' + acc + '</div>' +
      '<h2>Оформление</h2><div class="itc-group"><div class="itc-field"><span>Тема</span>' + seg('theme', [['system', 'Системная'], ['light', 'Светлая'], ['dark', 'Тёмная']], pr.theme) + '</div>' +
      '<div class="itc-field"><span>Размер текста</span>' + seg('textSize', [['normal', 'Обычный'], ['large', 'Крупный'], ['xlarge', 'Очень крупный']], pr.textSize) + '</div>' +
      '<div class="itc-field"><span>Акцентный цвет</span><div class="itc-swatches" role="radiogroup" data-seg="accent">' + ACC.map(function (a) {
        return '<button type="button" role="radio" class="itc-sw" data-accent="' + a[0] + '" data-v="' + a[0] + '" aria-label="' + a[1] + '" aria-checked="' + (a[0] === pr.accent) + '"></button>'; }).join('') + '</div></div></div>' +
      '<h2>Уведомления</h2><div class="itc-group"><label class="itc-row itc-row-sw"><span class="itc-row-tx"><span>Вибрация</span><small>Короткий отклик на нажатия</small></span><input type="checkbox" role="switch" class="itc-switch" data-haptics' + (Haptics.on() ? ' checked' : '') + '></label><div data-ext="notify"></div></div>' +
      '<h2>О приложении</h2><div class="itc-group">' + row('Проверить обновления', { act: 'update' }) +
      '<div class="itc-row itc-row-static"><span class="itc-row-tx"><span>Версия</span></span><span class="itc-row-val">' + esc(window.ITC_VERSION || '—') + '</span></div>' +
      '<div class="itc-row itc-row-static"><span class="itc-row-tx"><span>Разработчик</span></span><span class="itc-row-val">ИТС КИПФИН</span></div></div>' +
      (DEV ? '<h2>Для разработчиков</h2><div class="itc-group" data-ext="dev"></div>' : '') +
      '</div></div>', 'itc-ob-scroll itc-settings');
    exts.forEach(function (fn) { try { fn(s.querySelector('[data-ext="dev"]'), { row: row, close: s.close, section: 'dev', screen: s }); } catch (e) { console.warn(e); } });
    s.querySelector('[data-haptics]').addEventListener('change', function () { Haptics.set(this.checked); if (this.checked) Haptics.tap(); });
    s.addEventListener('click', async function (e) {
      var sg = e.target.closest('[data-seg] [data-v]');
      if (sg) {
        var k = sg.closest('[data-seg]').getAttribute('data-seg'), o = {}; o[k] = sg.getAttribute('data-v');
        if (T) T.set(o); sg.parentNode.querySelectorAll('[data-v]').forEach(function (x) { x.setAttribute('aria-checked', String(x === sg)); }); Haptics.tap(); return;
      }
      var b = e.target.closest('[data-act]'); if (!b) return;
      var a = b.getAttribute('data-act'); Haptics.tap();
      if (a === 'close') { s.close(); return; }
      if (a === 'logout') {
        if (!confirm('Выйти из аккаунта сотрудника?')) return;
        await Session.logout(); s.close(); toast('Вы вышли'); location.href = '/'; return;
      }
      s.close();
      if (a === 'admin-login') location.href = '/admin/login.html';
      else if (a === 'admin') location.href = '/admin/index.html';
      else if (a === 'update') { if (window.ItcAppUpdate) window.ItcAppUpdate.check({ manual: true }); else toast('Обновления проверяются только в приложении'); }
    });
  }
  window.ItcSettings = { open: settingsScreen, row: row };

  // ---------- t99: запуск и разделение ролей ----------
  // admin → админка; гость → расписание. Не-админ в /admin/* → вход для сотрудников.
  function roleHomeChip() {
    var r = Session.role(); if (r !== 'admin') return;
    var h = document.querySelector('body.campus-page:not(.admin-page) > .campus-header'); if (!h || h.querySelector('.itc-home-chip')) return;
    var a = el('<a class="itc-home-chip" href="/admin/index.html">Админка</a>');
    var g = h.querySelector('.app-gear'); if (g) h.insertBefore(a, g); else h.appendChild(a);
  }
  function boot() {
    var p = location.pathname, q = new URLSearchParams(location.search), r = Session.role();
    var NATIVE = window.Capacitor && Capacitor.isNativePlatform && Capacitor.isNativePlatform();
    if (/^\/admin\//.test(p) && !/login/.test(p)) { if (NATIVE && r !== 'admin') location.replace('/admin/login.html'); return; }
    if (/^\/admin\//.test(p) || /settings\.html$/.test(p)) return;
    var home = p === '/' || /\/index\.html$/.test(p);
    if (home && !r) { setTimeout(roleScreen, window.ItcSplash ? 700 : 0); return; }
    var cold = home && !sessionStorage.getItem('itc.launched') && !q.get('from'); sessionStorage.setItem('itc.launched', '1');
    if (cold && r === 'admin') { location.replace('/admin/index.html'); return; }
    roleHomeChip(); setTimeout(roleHomeChip, 400);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
