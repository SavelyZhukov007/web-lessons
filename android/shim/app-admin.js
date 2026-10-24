/* Админка в APK (только Capacitor): без крупных заголовков разделов (контент выше), понятная связка
 * «Кружки» (карточки: что за кружок) ⇄ «Расписание» (когда, где, кто — бывшие «Занятия»), перекрёстные ссылки,
 * подсказки в пустых состояниях, метки параллельных занятий. Веб-админка сайта не меняется. */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  if (!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform())) return;
  if (!/^\/admin\//.test(location.pathname) || /login/.test(location.pathname)) return;
  var doc = document;
  var HINTS = {
    clubs: 'Кружок — это карточка: название, направление, руководитель, описание. Когда и где он проходит — во вкладке «Расписание».',
    sessions: 'Расписание — когда, где и у кого проходят кружки. Параллельно можно в разных аудиториях; одна аудитория или один руководитель в одно время — нельзя.'
  };
  var EMPTY = {
    'Кружков пока нет': 'Добавьте первый кружок кнопкой «Добавить кружок». Потом задайте ему время в «Расписании».',
    'Занятий пока нет': 'Сначала создайте кружок во вкладке «Кружки», затем добавьте ему день, время и аудиторию здесь.'
  };
  function route() { return location.hash.replace(/^#\/?/, '').split(/[/?]/)[0]; }
  function rename() {
    doc.querySelectorAll('[data-route="sessions"]').forEach(function (a) {
      var l = a.querySelector('.bn-label') || a;
      if (l.textContent === 'Занятия') l.textContent = 'Расписание';
    });
    doc.querySelectorAll('[data-route="clubs"]').forEach(function (a) { a.title = 'Кружки — карточки кружков'; });
  }
  function hint(main, r) {
    var old = main.querySelector('.app-admin-hint');
    if (!HINTS[r]) { if (old) old.remove(); return; }
    if (old && old.getAttribute('data-r') === r) return;
    if (old) old.remove();
    var p = doc.createElement('p'); p.className = 'app-admin-hint'; p.setAttribute('data-r', r); p.textContent = HINTS[r];
    var anchor = main.querySelector('#native-sessions-tabs') || main.querySelector('.admin-head');
    if (anchor) anchor.insertAdjacentElement('afterend', p);
  }
  function empties(main) {
    main.querySelectorAll('.empty-state:not([data-app-hint])').forEach(function (e) {
      var t = (e.querySelector('strong') || e).textContent.trim();
      if (!EMPTY[t]) return;
      e.setAttribute('data-app-hint', '');
      var p = doc.createElement('p'); p.className = 'field-hint'; p.textContent = EMPTY[t]; e.appendChild(p);
    });
  }
  // «Кружки» → число занятий ссылкой на расписание этого кружка; «Расписание» → название кружка ссылкой на карточку
  function crossLinks(main, r) {
    if (r === 'clubs') main.querySelectorAll('td[data-label="Занятий"]:not([data-app-link])').forEach(function (td) {
      td.setAttribute('data-app-link', '');
      var name = (td.parentNode.querySelector('td[data-label="Название"] strong') || {}).textContent;
      var n = td.textContent.trim();
      var a = doc.createElement('a'); a.href = '#/sessions'; a.className = 'app-xlink';
      a.textContent = n === '0' ? 'Добавить время →' : n + ' в расписании →';
      a.addEventListener('click', function () { sessionStorage.setItem('itc.adm.club', name || ''); });
      td.replaceChildren(a);
    });
    if (r === 'sessions') {
      main.querySelectorAll('td[data-label="Кружок"]:not([data-app-link])').forEach(function (td) {
        td.setAttribute('data-app-link', '');
        var s = td.querySelector('strong'); if (!s) return;
        var a = doc.createElement('a'); a.href = '#/clubs'; a.className = 'app-xlink strong'; a.textContent = s.textContent;
        a.title = 'Открыть карточку кружка';
        a.addEventListener('click', function () { sessionStorage.setItem('itc.adm.clubq', s.textContent); });
        td.replaceChildren(a);
      });
      parallel(main);
    }
  }
  // применяем «переход по ссылке»: фильтр по кружку в расписании, поиск в «Кружках»
  function applyJump(main, r) {
    var name, sel;
    if (r === 'sessions' && (name = sessionStorage.getItem('itc.adm.club')) !== null) {
      sel = main.querySelector('select[aria-label="Кружок"]'); if (!sel) return;
      sessionStorage.removeItem('itc.adm.club');
      for (var i = 0; i < sel.options.length; i++) if (sel.options[i].textContent === name) { sel.value = sel.options[i].value; sel.dispatchEvent(new Event('change')); break; }
    }
    if (r === 'clubs' && (name = sessionStorage.getItem('itc.adm.clubq')) !== null) {
      var q = main.querySelector('input[type="search"]'); if (!q) return;
      sessionStorage.removeItem('itc.adm.clubq');
      q.value = name; q.dispatchEvent(new Event('input'));
    }
  }
  function mins(t) { var p = t.split(':'); return +p[0] * 60 + +p[1]; }
  function parallel(main) {
    var rows = [].slice.call(main.querySelectorAll('table.data tbody tr')).map(function (tr) {
      var c = function (l) { var td = tr.querySelector('td[data-label="' + l + '"]'); return td ? td.textContent.trim() : ''; };
      var t = c('Время').replace(/\s*(параллельно|конфликт).*/, '').split(/[–-]/);
      return { tr: tr, day: c('День'), s: mins(t[0] || '0:0'), e: mins(t[1] || '0:0'), room: c('Аудитория'), leader: c('Руководитель') };
    });
    rows.forEach(function (a) {
      var par = 0, conflict = false;
      rows.forEach(function (b) { if (a === b || a.day !== b.day || !(a.s < b.e && b.s < a.e)) return; par++; if (a.room === b.room || a.leader === b.leader) conflict = true; });
      var td = a.tr.querySelector('td[data-label="Время"]'); if (!td) return;
      var old = td.querySelector('.app-par'); if (old) old.remove();
      if (!par) return;
      var b = doc.createElement('span'); b.className = 'app-par badge' + (conflict ? ' conflict' : '');
      b.textContent = conflict ? 'конфликт' : 'параллельно · ' + (par + 1); b.title = conflict ? 'Та же аудитория или руководитель в это время' : 'В это время идут и другие занятия (в других аудиториях)';
      td.appendChild(b);
    });
  }
  var pend = false;
  function patch() {
    pend = false;
    var main = doc.getElementById('admin-main'); if (!main) return;
    rename();
    if (main.getAttribute('aria-busy') === 'true') return;
    var r = route();
    hint(main, r); empties(main); crossLinks(main, r); applyJump(main, r);
  }
  function start() { patch(); new MutationObserver(function () { if (!pend) { pend = true; requestAnimationFrame(patch); } }).observe(doc.body, { childList: true, subtree: true }); }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start); else start();
})();
