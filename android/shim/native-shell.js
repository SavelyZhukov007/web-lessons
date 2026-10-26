/* Нативная оболочка APK (Capacitor). Подключается prepare-web.mjs ТОЛЬКО в www/ приложения, сразу после shim.
 * Ничего не делает вне Capacitor.isNativePlatform(): сайт (frontend/) не меняется вообще.
 * Ставит <html class="is-native"> (под ним вся вёрстка из css/native-shell.css) и добавляет нативное поведение:
 * системные бары по теме, кнопка «Назад» Android, запись в календарь устройства, выход/вход, бренд «KipClub». */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  var NATIVE = !!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform());
  var PWA = !NATIVE && window.ItcPwa === true; // установленное PWA (standalone) — флаг ставит pwa-standalone.js только в сборке pwa
  if (!NATIVE && !PWA) return;
  var doc = document, root = doc.documentElement;
  root.classList.add('is-native');
  var P = (NATIVE && Cap.Plugins) || {};
  var DEMO_LOGGED_OUT = 'itc.demo.loggedOut';

  // css/native-shell.css — последним в <head>, чтобы перекрывать стили сайта
  function addCss() {
    if (doc.querySelector('link[data-native-shell]')) return;
    var l = doc.createElement('link'); l.rel = 'stylesheet'; l.href = '/css/native-shell.css'; l.setAttribute('data-native-shell', '');
    (doc.head || root).appendChild(l);
  }
  addCss();
  doc.addEventListener('DOMContentLoaded', function () { var l = doc.querySelector('link[data-native-shell]'); if (l && l.nextElementSibling) doc.head.appendChild(l); });

  function toast(msg) { import('/js/ui.js').then(function (m) { m.toast(msg); }).catch(function () { alert(msg); }); }

  // ---------- 8. Системные бары: иконки статус-бара/навигации по теме приложения (а не только системы)
  function syncBars() {
    var dark = root.getAttribute('data-theme') === 'dark';
    var style = dark ? 'DARK' : 'LIGHT'; // DARK = светлые иконки на тёмном фоне
    try { if (P.SystemBars && P.SystemBars.setStyle) P.SystemBars.setStyle({ style: style }).catch(function () { }); } catch (e) { }
    try { if (P.StatusBar && P.StatusBar.setStyle) P.StatusBar.setStyle({ style: style }).catch(function () { }); } catch (e) { }
  }
  syncBars();
  new MutationObserver(syncBars).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  doc.addEventListener('visibilitychange', function () { if (!doc.hidden) syncBars(); });

  // ---------- 11 / 6 / 10. Точечные правки DOM (бренд, иконка аккаунта, подпись кнопки календаря)
  var LOCK_EDIT = ['M5 11h10v9H5z', 'M7.5 11V8a2.5 2.5 0 0 1 5 0v3', 'M10 15v1.5', 'M14.5 21l.6-2.6 4.6-4.6 2 2-4.6 4.6z'];
  function patchDom() {
    doc.querySelectorAll('.campus-brand > span:not(.native-brand)').forEach(function (s) {
      var t = s.firstChild;
      if (t && t.nodeType === 3 && /кружки|kipclub/i.test(t.nodeValue)) { t.nodeValue = 'KipClub'; s.classList.add('native-brand'); }
      var small = s.parentNode.querySelector('small');
      if (small && /КИПФИН/.test(small.textContent)) small.remove();
      if (/главная/.test(s.parentNode.getAttribute('aria-label') || '')) s.parentNode.setAttribute('aria-label', 'KipClub — главная');
    });
    doc.querySelectorAll('a.settings-button[href="#/account"]:not([data-native-icon])').forEach(function (a) {
      var svg = a.querySelector('svg'); if (!svg) return;
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      LOCK_EDIT.forEach(function (d) { var p = doc.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); svg.appendChild(p); });
      a.setAttribute('data-native-icon', '');
      var login = (a.getAttribute('aria-label') || '').replace(/^Аккаунт:\s*/, '');
      a.setAttribute('aria-label', 'Аккаунт и смена пароля' + (login ? ': ' + login : '')); a.title = 'Аккаунт и смена пароля';
    });
    doc.querySelectorAll('a[href*="/calendar.ics"]:not([data-native-cal])').forEach(function (a) {
      a.setAttribute('data-native-cal', '');
      for (var n = a.lastChild; n; n = n.previousSibling) if (n.nodeType === 3 && n.nodeValue.trim()) { n.nodeValue = /[?&]week=/.test(a.getAttribute('href')) ? 'Добавить в календарь — текущая неделя' : 'Добавить в календарь'; break; }
    });
    if (window.DemoBackend && /^\/admin\/login(\.html)?$/.test(location.pathname)) addDemoLogin();
    // без подсказок для разработчиков (reset-password в консоли сервера)
    doc.querySelectorAll('p.field-hint:not([data-native-hidden])').forEach(function (p) {
      if (/reset-password|server\.py/.test(p.textContent)) { p.setAttribute('data-native-hidden', ''); p.hidden = true; }
    });
    if (doc.getElementById('admin-main')) mergeReference();
    if (NATIVE || PWA) appHeader(); // PWA (iPhone/Android standalone): та же шапка с ⚙ — иначе native-shell.css прячет кнопку сайта, а замены нет
    wireSearch();
  }
  // ---------- F2 / t99. Шапка APK: ссылка-переключатель («Все кружки» ⇄ «Расписание») + шестерёнка «Настройки».
  // Нажатие — экран настроек (window.ItcSettings из app-student.js), долгое нажатие — сразу к расписанию.
  var GEAR = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>';
  function gearButton() {
    var btn = doc.createElement('button');
    btn.type = 'button'; btn.className = 'app-menu-btn app-gear'; btn.id = 'app-menu-btn';
    btn.setAttribute('aria-label', 'Настройки (удерживайте — к расписанию)'); btn.innerHTML = GEAR;
    var t = 0, longed = false;
    btn.addEventListener('pointerdown', function () {
      longed = false; clearTimeout(t); t = setTimeout(function () {
        longed = true; if (window.ItcHaptics) window.ItcHaptics.tap(); location.href = '/?from=gear';
      }, 550);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(function (ev) { btn.addEventListener(ev, function () { clearTimeout(t); }); });
    btn.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    btn.addEventListener('click', function (e) { e.stopPropagation(); if (longed) return; if (window.ItcSettings) window.ItcSettings.open(); else if (window.ClubsSettings) window.ClubsSettings.open(); });
    return btn;
  }
  function appHeader() {
    var ah = doc.querySelector('#admin-header');
    if (ah && ah.querySelector('.admin-tools') && !ah.querySelector('.app-gear')) { // админка перерисовывает шапку целиком — проверяем по шестерёнке // админка: верхние ссылки разделов дублируют нижнюю навигацию — убираем
      ah.setAttribute('data-native-admin', '');
      var an = ah.querySelector('.admin-nav'); if (an) an.remove();
      // «Расписание», «Сменить пароль» и «Выйти» — в Настройках (шестерёнка); в верхней панели только логотип и ⚙
      var tools = ah.querySelector('.admin-tools');
      tools.querySelectorAll('.settings-button').forEach(function (b) { b.remove(); });
      tools.appendChild(gearButton());
      return;
    }
    var header = doc.querySelector('body.campus-page:not(.admin-page) > .campus-header:not([data-app-header])');
    if (!header) return;
    header.setAttribute('data-app-header', '');
    var nav = header.querySelector('nav');
    var onSchedule = location.pathname === '/' || /\/index\.html$/.test(location.pathname);
    if (nav) {
      var a = doc.createElement('a');
      a.className = 'app-nav-toggle';
      a.href = onSchedule ? '/clubs.html' : '/';
      a.textContent = onSchedule ? 'Все кружки' : 'Расписание';
      nav.replaceChildren(a);
    }
    var staff = header.querySelector('.staff-link'); if (staff) staff.remove();
    header.querySelectorAll('[data-settings-button]').forEach(function (x) { x.remove(); });
    header.appendChild(gearButton());
  }
  function closeMenu() { }
  // ---------- 13. Поиск в расписании на Android: Enter/«Найти» на клавиатуре, русская IME-композиция, клавиатура не закрывает результаты
  function wireSearch() {
    doc.querySelectorAll('input[type="search"]:not([data-native-search]), input#search:not([data-native-search])').forEach(function (inp) {
      inp.setAttribute('data-native-search', '');
      inp.setAttribute('enterkeyhint', 'search');
      if (inp.type !== 'search') inp.type = 'search';
      var last = inp.value, composing = false;
      function live() { if (inp.value === last) return; last = inp.value; inp.dispatchEvent(new Event('input', { bubbles: true })); }
      inp.addEventListener('compositionstart', function () { composing = true; });
      inp.addEventListener('compositionend', function () { composing = false; setTimeout(live, 0); });
      // часть клавиатур во время композиции не шлёт input — подхватываем по keyup/таймеру
      inp.addEventListener('keyup', function () { setTimeout(live, 0); });
      inp.addEventListener('input', function () { last = inp.value; });
      function submit() {
        live();
        var form = inp.form;
        inp.blur(); // закрыть клавиатуру
        if (form) { if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })); }
        setTimeout(function () {
          var res = doc.getElementById('result-status') || doc.getElementById('content');
          if (res) res.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 350);
      }
      inp.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.keyCode === 13) { e.preventDefault(); submit(); }
      });
      // Android WebView при keyCode 229 (IME) иногда присылает Enter только как beforeinput insertLineBreak / search-событие
      inp.addEventListener('beforeinput', function (e) { if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') { e.preventDefault(); submit(); } });
      inp.addEventListener('search', function () { if (!composing) live(); });
    });
  }
  // клавиатура открыта: держим фокусный элемент над ней и даём странице место снизу
  if (window.visualViewport) {
    var vv = window.visualViewport;
    var onVV = function () {
      var kb = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      doc.documentElement.style.setProperty('--native-kb', kb > 80 ? kb + 'px' : '0px');
      doc.documentElement.classList.toggle('native-kb-open', kb > 80);
      var a = doc.activeElement;
      if (kb > 80 && a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) a.scrollIntoView({ block: 'center' });
    };
    vv.addEventListener('resize', onVV);
  }

  // ---------- 12. Справочники внутри «Занятий»: вкладки нижней навигации без «Справочников»,
  // на экране «Занятия» — сегменты «Расписание · Направления · Руководители · Аудитории» (#/reference/* работают как раньше)
  var REF_TABS = [['sessions', 'Расписание'], ['reference/categories', 'Направления'], ['reference/leaders', 'Руководители'], ['reference/rooms', 'Аудитории']];
  function mergeReference() {
    var hash = location.hash.replace(/^#\/?/, '');
    var route = hash.split('/')[0];
    var main = doc.getElementById('admin-main');
    var bar = doc.getElementById('native-sessions-tabs');
    if (route !== 'sessions' && route !== 'reference') { if (bar) bar.remove(); return; }
    var cur = route === 'sessions' ? route : 'reference/' + (hash.split('/')[1] || 'categories');
    doc.querySelectorAll('[data-route="sessions"]').forEach(function (a) { a.setAttribute('aria-current', 'page'); });
    if (!main.firstElementChild || main.getAttribute('aria-busy') === 'true') return;
    if (bar && bar.parentNode === main && bar.getAttribute('data-cur') === cur && bar.previousElementSibling === (main.querySelector('.admin-head') || main.firstElementChild)) return;
    if (bar) bar.remove();
    bar = doc.createElement('div');
    bar.id = 'native-sessions-tabs'; bar.className = 'segmented admin-tabs native-sessions-tabs'; bar.setAttribute('role', 'tablist');
    bar.setAttribute('aria-label', 'Разделы занятий'); bar.setAttribute('data-cur', cur);
    REF_TABS.forEach(function (t) {
      var a = doc.createElement('a'); a.href = '#/' + t[0]; a.setAttribute('role', 'tab'); a.textContent = t[1];
      a.setAttribute('aria-selected', String(t[0] === cur)); if (t[0] === cur) a.className = 'is-current';
      bar.appendChild(a);
    });
    var head = main.querySelector('.admin-head') || main.firstElementChild;
    if (route === 'reference') { var h = head.querySelector('h1, h2'); if (h) h.textContent = 'Занятия'; doc.title = 'Занятия — админка'; }
    head.insertAdjacentElement('afterend', bar);
  }
  var pending = false;
  function schedule() { if (pending) return; pending = true; requestAnimationFrame(function () { pending = false; patchDom(); }); }
  function startObserver() { patchDom(); new MutationObserver(schedule).observe(doc.body, { childList: true, subtree: true }); }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', startObserver); else startObserver();

  // ---------- 7. Вход/выход. Демо: «Войти как админ»; явный выход запоминается (demo-backend.js перестаёт входить сам)
  function addDemoLogin() {
    var form = doc.querySelector('#login-form');
    if (!form || doc.querySelector('[data-native-demo-login]') || window.ITC_CHANNEL === 'p') return; // p: без демо-входа одной кнопкой
    var btn = doc.createElement('button');
    btn.type = 'button'; btn.className = 'btn btn--tonal btn--block'; btn.textContent = 'Войти как админ';
    btn.addEventListener('click', function () {
      var admin = window.DemoBackend && window.DemoBackend._db().admins[0];
      if (!admin) return;
      form.elements.login.value = admin.login; form.elements.password.value = admin.password;
      if (form.requestSubmit) form.requestSubmit(); else form.querySelector('button[type=submit]').click();
    });
    var box = doc.createElement('div'); box.className = 'native-demo-login'; box.setAttribute('data-native-demo-login', '');
    box.appendChild(btn);
    form.appendChild(box);
    if (/[?&]demo=1/.test(location.search) && window.ITC_CHANNEL === 'l') setTimeout(function () { btn.click(); }, 50);
  }
  // Флаг «вышел явно» ставит сам demo-backend на POST /api/admin/logout; здесь — только на случай, если запрос не дошёл.
  window.addEventListener('click', function (e) {
    var b = e.target && e.target.closest && e.target.closest('button');
    if (b && window.DemoBackend && /^Выйти$/.test((b.getAttribute('aria-label') || b.textContent || '').trim())) {
      try { localStorage.setItem(DEMO_LOGGED_OUT, '1'); } catch (x) { }
    }
  }, true);

  // ---------- 10. «Добавить в календарь»: календарь устройства (плагин) → иначе .ics через Filesystem + Share
  var MSK = 'Europe/Moscow';
  function mskEpoch(y, m, d, hm) { var t = hm.split(':'); return Date.UTC(y, m, d, +t[0] - 3, +t[1]); } // МСК = UTC+3 круглый год
  function mskToday() { var n = new Date(Date.now() + 3 * 3600000); return { y: n.getUTCFullYear(), m: n.getUTCMonth(), d: n.getUTCDate(), wd: n.getUTCDay() || 7 }; }
  function semesterEnd() { var t = mskToday(); var y = t.m >= 6 ? t.y + 1 : t.y; return Date.UTC(y, 5, 30, 20, 59); } // до 30 июня учебного года
  function firstOccurrence(weekday) { var t = mskToday(); var diff = (weekday - t.wd + 7) % 7; var dt = new Date(Date.UTC(t.y, t.m, t.d + diff)); return { y: dt.getUTCFullYear(), m: dt.getUTCMonth(), d: dt.getUTCDate() }; }
  function pad(n) { return String(n).padStart(2, '0'); }
  function icsDate(ms) { var d = new Date(ms); return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + 'T' + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + '00Z'; }
  function esc(s) { return String(s || '').replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/([,;])/g, '\\$1'); }
  var BYDAY = ['', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];

  function plan(club) {
    var until = semesterEnd();
    var cancelled = (club.upcoming_exceptions || []).filter(function (x) { return x.type === 'cancelled' || x.type === 'moved'; });
    return (club.sessions || []).map(function (s) {
      var f = firstOccurrence(s.weekday);
      var start = mskEpoch(f.y, f.m, f.d, s.start_time), end = mskEpoch(f.y, f.m, f.d, s.end_time);
      var ex = cancelled.filter(function (x) { return x.session_id === s.id; }).map(function (x) { var p = x.original_date.split('-'); return mskEpoch(+p[0], +p[1] - 1, +p[2], s.start_time); });
      var room = s.room ? s.room.name + (s.room.building ? ', ' + s.room.building : '') : '';
      return {
        session: s, start: start, end: end, until: until, exdates: ex, location: room,
        title: club.name, description: [club.leader ? 'Руководитель: ' + club.leader.name : '', 'Расписание кружков ИТС'].filter(Boolean).join('\n')
      };
    });
  }
  function buildIcs(club, items) {
    var L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ITC Kruzhki app//RU', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'];
    var stamp = icsDate(Date.now());
    items.forEach(function (it) {
      L.push('BEGIN:VEVENT', 'UID:club-' + club.id + '-session-' + it.session.id + '@itc-kruzhki', 'DTSTAMP:' + stamp,
        'DTSTART:' + icsDate(it.start), 'DTEND:' + icsDate(it.end),
        'RRULE:FREQ=WEEKLY;BYDAY=' + BYDAY[it.session.weekday] + ';UNTIL=' + icsDate(it.until));
      if (it.exdates.length) L.push('EXDATE:' + it.exdates.map(icsDate).join(','));
      L.push('SUMMARY:' + esc(it.title), 'LOCATION:' + esc(it.location), 'DESCRIPTION:' + esc(it.description), 'END:VEVENT');
    });
    L.push('END:VCALENDAR');
    return L.join('\r\n') + '\r\n';
  }
  function toDeviceCalendar(items) {
    var C = P.CapacitorCalendar;
    if (!C || !C.createEvent) return Promise.reject(new Error('no-plugin'));
    var ask = C.requestWriteOnlyCalendarAccess ? C.requestWriteOnlyCalendarAccess() : C.requestFullCalendarAccess();
    return ask.then(function (r) {
      if (!r || r.result !== 'granted') throw new Error('denied');
      return items.reduce(function (p, it) {
        return p.then(function (n) {
          return C.createEvent({
            title: it.title, location: it.location, description: it.description, startDate: it.start, endDate: it.end,
            alerts: [-30], recurrence: { frequency: 'weekly', interval: 1, byWeekDay: [it.session.weekday], end: it.until }
          }).then(function () { return n + 1; });
        });
      }, Promise.resolve(0));
    });
  }
  function shareIcs(club, items) {
    var FS = P.Filesystem, SH = P.Share;
    if (PWA) return webIcs(club, items);
    if (!FS || !SH) return Promise.reject(new Error('no-fs'));
    var name = 'club-' + club.id + '.ics';
    return FS.writeFile({ path: name, data: buildIcs(club, items), directory: 'CACHE', encoding: 'utf8' })
      .then(function (r) { return SH.share({ title: club.name, text: 'Расписание: ' + club.name, files: [r.uri], dialogTitle: 'Открыть в календаре' }); });
  }
  // PWA: .ics на весь семестр (еженедельные RRULE + EXDATE отмен) — системное «Поделиться» (iOS: «Календарь») или скачивание файла
  function webIcs(club, items) {
    return webCalendarFile(club.name, 'club-' + club.id + '.ics', buildIcs(club, items));
  }
  function webCalendarFile(title, name, text) {
    var file = null;
    try { file = new File([text], name, { type: 'text/calendar' }); } catch (e) { /* старый WebKit */ }
    if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
      return navigator.share({ files: [file], title: title }).then(function () { return 'shared'; }, function (e) {
        if (e && e.name === 'AbortError') return 'cancel';
        return download(text, name);
      });
    }
    return Promise.resolve(download(text, name));
  }
  function download(text, name) {
    var ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (ios) { location.href = 'data:text/calendar;charset=utf-8,' + encodeURIComponent(text); return 'opened'; } // iOS открывает «Добавить в Календарь»
    var url = URL.createObjectURL(new Blob([text], { type: 'text/calendar;charset=utf-8' }));
    var a = doc.createElement('a'); a.href = url; a.download = name; a.setAttribute('data-itc-ics', ''); doc.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1500);
    return 'downloaded';
  }
  var busy = false;
  window.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href*="/calendar.ics"]:not([data-itc-ics])');
    if (!a) return;
    e.preventDefault(); e.stopImmediatePropagation(); // раньше обработчиков shim/demo-backend (они на document)
    if (busy) return; busy = true; a.setAttribute('aria-busy', 'true');
    var href = a.getAttribute('href');
    if (/[?&]week=/.test(href)) {
      // Общий контракт с сайтом: готовая выбранная неделя с реальными отменами и переносами.
      fetch(href, { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
        .then(function (text) {
          if (!/^BEGIN:VCALENDAR/m.test(text)) throw new Error('Некорректный файл календаря');
          var name = 'club-' + ((href.match(/\/clubs\/(\d+)\//) || [])[1] || 'schedule') + '-week.ics';
          if (PWA) return webCalendarFile('Расписание на неделю', name, text);
          if (P.Filesystem && P.Share) return P.Filesystem.writeFile({ path: name, data: text, directory: 'CACHE', encoding: 'utf8' })
            .then(function (r) { return P.Share.share({ title: 'Расписание на неделю', files: [r.uri] }); });
          return download(text, name);
        }).catch(function (err) { if (err.name !== 'AbortError') toast('Не удалось сохранить календарь: ' + err.message); })
        .finally(function () { busy = false; a.removeAttribute('aria-busy'); });
      return;
    }
    var id = (a.getAttribute('href').match(/\/clubs\/(\d+)\//) || [])[1];
    fetch('/api/clubs/' + id).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (club) {
        var items = plan(club);
        if (!items.length) { toast('У кружка пока нет занятий в расписании'); return; }
        if (PWA) return webIcs(club, items).then(function (r) { if (r === 'downloaded') toast('Файл календаря сохранён — откройте его, чтобы добавить занятия'); });
        return toDeviceCalendar(items).then(function (n) {
          toast(n === 1 ? 'Занятие добавлено в календарь (повторяется еженедельно)' : 'Добавлено в календарь: ' + n + ' еженедельных занятия');
        }, function (err) {
          console.warn('[native-shell] calendar plugin:', err && err.message);
          if (err && err.message === 'denied') toast('Нет доступа к календарю — открываю файл .ics');
          return shareIcs(club, items).catch(function (e2) { if (!/cancel/i.test(String(e2 && e2.message))) throw e2; });
        });
      })
      .catch(function (err) { toast('Не удалось добавить в календарь: ' + (err && err.message || err)); })
      .then(function () { busy = false; a.removeAttribute('aria-busy'); });
  }, true);

  // ---------- 9. Кнопка/жест «Назад»: окно → панель фильтров → предыдущий экран → свернуть на корневом
  function isRoot() { return location.pathname === '/' || location.pathname === '/index.html'; }
  function onBack(ev) {
    var sheet = doc.querySelector('#itc-sheet, #app-update-sheet:not([data-forced])');
    if (sheet) { var c0 = sheet.querySelector('.itc-close, [data-later]'); if (c0) c0.click(); else sheet.remove(); return; }
    var dlg = doc.querySelectorAll('dialog[open]');
    if (dlg.length) {
      var d = dlg[dlg.length - 1];
      if (typeof d.requestClose === 'function') d.requestClose();
      else { var c = new Event('cancel', { cancelable: true }); if (d.dispatchEvent(c)) d.close(); }
      return;
    }
    var filt = doc.querySelector('#toggle-filters[aria-expanded="true"]');
    if (filt && filt.offsetParent) { filt.click(); return; }
    var path = location.pathname;
    if (isRoot()) { if (P.App && P.App.minimizeApp) P.App.minimizeApp(); else if (P.App) P.App.exitApp(); return; }
    if (/^\/admin\/login/.test(path) || /^\/settings\.html$/.test(path)) { location.replace('/'); return; }
    if (/^\/admin\//.test(path) && location.hash && location.hash !== '#/' && location.hash !== '#') { history.back(); return; }
    if (/^\/admin\//.test(path)) { location.href = '/'; return; }
    if (ev && ev.canGoBack) history.back(); else location.replace('/');
  }
  if (P.App && P.App.addListener) P.App.addListener('backButton', onBack);
  window.NativeShell = { back: onBack, buildIcs: buildIcs, plan: plan, webIcs: PWA ? webIcs : null, host: NATIVE ? 'native' : 'pwa' };
})();
