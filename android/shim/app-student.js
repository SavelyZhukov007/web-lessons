/* Роли и анонимная посещаемость в APK.
 * «Я студент»: ФИО и группа хранятся ТОЛЬКО на устройстве, зашифрованно (Android Keystore через ItcSecure; в браузере —
 * WebCrypto AES-GCM с неэкспортируемым ключом в IndexedDB). На сервер уходит только ID: S- + base32(HMAC-SHA256(секрет
 * устройства 256 бит, «фио|ГРУППА»))[:128 бит]. Резервный код = секрет (восстановление на новом телефоне).
 * «Я преподаю»: вход по идентификатору T-… (выдаёт администратор) → только свои кружки, QR занятия и отметки. */
(function () {
  'use strict';
  var LS = window.localStorage, P = (window.Capacitor && window.Capacitor.Plugins) || {};
  var ROLE_KEY = 'itc.role', VAULT_KEY = 'itc.vault.v1', TSES = 'itc.teacher.session';
  var B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  var GROUP_RE = /^[1-6][А-ЯЁ]{2,10}-\d{3,4}$/; // {курс}{специальность}-{номер группы}: 1ИСИП-126

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
  function b32(bytes) { var bits = 0, val = 0, out = ''; for (var i = 0; i < bytes.length; i++) { val = (val << 8) | bytes[i]; bits += 8; while (bits >= 5) { out += B32[(val >>> (bits - 5)) & 31]; bits -= 5; } } if (bits > 0) out += B32[(val << (5 - bits)) & 31]; return out; }
  function unb32(s) { s = s.replace(/[^A-Z2-7]/gi, '').toUpperCase(); var bits = 0, val = 0, out = []; for (var i = 0; i < s.length; i++) { val = (val << 5) | B32.indexOf(s[i]); bits += 5; if (bits >= 8) { out.push((val >>> (bits - 8)) & 255); bits -= 8; } } return new Uint8Array(out); }
  function b64u(bytes) { var s = ''; for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
  function b64dec(s) { var t = atob(s.replace(/-/g, '+').replace(/_/g, '/')); var a = new Uint8Array(t.length); for (var i = 0; i < t.length; i++) a[i] = t.charCodeAt(i); return a; }
  function grp(prefix, t) { return prefix + '-' + t.match(/.{1,4}/g).join('-'); }
  function rand(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return a; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function el(html) { var d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function toast(t) { if (window.ItcFeatures && window.ItcFeatures.toast) window.ItcFeatures.toast(clean(t) || HUMAN[0]); }
  async function hmac(keyBytes, text) {
    var k = await crypto.subtle.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    return new Uint8Array(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(text)));
  }
  function normFio(p) { return [p.last, p.first, p.noMiddle ? '' : p.middle].join(' ').toLowerCase().replace(/ё/g, 'е').split(/\s+/).filter(Boolean).join(' '); }
  function normGroup(g) { return String(g || '').toUpperCase().replace(/\s+/g, ''); }
  /** S-ID — совпадает с эталоном backend/tests/test_attendance.py::student_id */
  async function computeId(secret, p) { var mac = await hmac(secret, normFio(p) + '|' + normGroup(p.group)); return grp('S', b32(mac.slice(0, 16)).slice(0, 26)); }
  async function deviceToken(secret) { return b64u(await hmac(secret, 'device-token')); }

  // ---------- шифрованное хранилище ----------
  var Vault = {
    native: function () { return !!(P.ItcSecure && P.ItcSecure.encrypt); },
    _key: function () {
      return new Promise(function (ok, fail) {
        var rq = indexedDB.open('itc-secure', 1);
        rq.onupgradeneeded = function () { rq.result.createObjectStore('keys'); };
        rq.onerror = function () { fail(rq.error); };
        rq.onsuccess = function () {
          var db = rq.result, tx = db.transaction('keys', 'readonly'), g = tx.objectStore('keys').get('k');
          g.onsuccess = function () {
            if (g.result) return ok(g.result);
            crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']).then(function (k) {
              var w = db.transaction('keys', 'readwrite'); w.objectStore('keys').put(k, 'k'); w.oncomplete = function () { ok(k); }; w.onerror = function () { fail(w.error); };
            }, fail);
          };
        };
      });
    },
    get: async function () {
      var ct = LS.getItem(VAULT_KEY); if (!ct) return null;
      try {
        var plain;
        if (ct.indexOf('n1:') === 0) plain = (await P.ItcSecure.decrypt({ ct: ct.slice(3) })).plain;
        else { var raw = b64dec(ct.slice(3)), k = await Vault._key(); plain = new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: raw.slice(0, 12) }, k, raw.slice(12))); }
        return JSON.parse(plain);
      } catch (e) { console.warn('[itc] профиль не расшифрован', e); return null; }
    },
    set: async function (obj) {
      var plain = JSON.stringify(obj);
      if (Vault.native()) { LS.setItem(VAULT_KEY, 'n1:' + (await P.ItcSecure.encrypt({ plain: plain })).ct); return; }
      var k = await Vault._key(), iv = rand(12), ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, k, new TextEncoder().encode(plain)));
      var all = new Uint8Array(12 + ct.length); all.set(iv); all.set(ct, 12); LS.setItem(VAULT_KEY, 'w1:' + b64u(all));
    },
    wipe: async function () { LS.removeItem(VAULT_KEY); try { if (Vault.native() && P.ItcSecure.wipe) await P.ItcSecure.wipe(); } catch (e) { /* нет ключа */ } },
  };

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

  // ---------- t99: единая сессия {role: guest|student|teacher|admin, name, exp} ----------
  // Секреты (ключ ID студента, идентификатор преподавателя) — в Vault (Android Keystore); здесь только роль и имя для UI.
  // Админ: токены выдаёт и хранит админка сайта (clubs.adminToken / clubs.adminRefresh); роль ставится по успешному
  // POST /api/admin/login и снимается по /api/admin/logout или 401 при обновлении. Срок — по refresh_expires_in.
  var SES_KEY = 'itc.session', ROLES = { guest: 'Гость', student: 'Студент', teacher: 'Преподаватель', admin: 'Сотрудник' };
  var Session = {
    get: function () {
      var v = null; try { v = JSON.parse(LS.getItem(SES_KEY)); } catch (e) { /* битое */ }
      if (!v) { var old = LS.getItem(ROLE_KEY); if (!old) return null; v = { role: old }; } // миграция с itc.role
      if (!ROLES[v.role]) return null;
      if (v.exp && v.exp < Date.now() && v.role !== 'guest' && v.role !== 'student') { // истёк вход сотрудника/преподавателя
        if (v.role === 'admin') { LS.removeItem('clubs.adminToken'); LS.removeItem('clubs.adminRefresh'); }
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
      syncShortcuts(role);
      return v;
    },
    logout: async function () {
      var r = Session.role();
      if (r === 'teacher') await Teacher.logout();
      if (r === 'admin') {
        try { await fetch('/api/admin/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + (LS.getItem('clubs.adminToken') || '') } }); } catch (e) { /* без сети — всё равно выходим локально */ }
        LS.removeItem('clubs.adminToken'); LS.removeItem('clubs.adminRefresh');
      }
      Session.set('guest');
    },
  };
  window.ItcSession = Session;
  function syncShortcuts(role) { try { if (P.ItcNative && P.ItcNative.roleShortcuts) P.ItcNative.roleShortcuts({ role: role || Session.role() }).catch(function () {}); } catch (e) { /* веб */ } }
  setTimeout(function () { syncShortcuts(); }, 1500);
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

  // ---------- студент ----------
  var cache = null;
  var Student = {
    role: function () { return Session.role(); },
    load: async function () {
      if (cache) return cache;
      var v = await Vault.get(); if (!v || !v.secret) return null;
      var secret = unb32(v.secret);
      cache = { profile: v.profile, secret: secret, id: await computeId(secret, v.profile), device: await deviceToken(secret) };
      return cache;
    },
    save: async function (profile, secret) {
      secret = secret || (cache && cache.secret) || rand(32);
      await Vault.set({ v: 1, profile: profile, secret: b32(secret) });
      cache = null; Session.set('student', [profile.first, profile.last].join(' ')); return Student.load();
    },
    backupCode: function (secret) { return grp('R', b32(secret)); },
    parseBackup: function (code) { var t = String(code || '').replace(/^itc-backup1:/, '').replace(/[\s-]/g, '').toUpperCase(); if (t[0] === 'R') t = t.slice(1); return /^[A-Z2-7]{52}$/.test(t) ? unb32(t).slice(0, 32) : null; },
    validate: function (p) {
      var err = {};
      ['last', 'first'].forEach(function (k) { if (!/^[А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z' -]{0,59}$/.test((p[k] || '').trim())) err[k] = 'Только буквы, дефис и пробел'; });
      if ((p.middle || '').trim() && !/^[А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z' -]{0,59}$/.test(p.middle.trim())) err.middle = 'Только буквы, дефис и пробел (или оставьте пустым)';
      var g = normGroup(p.group);
      if (!g) err.group = 'Укажите группу, например 1ИСИП-126';
      else if (!GROUP_RE.test(g)) err.group = /^[1-6]/.test(g) ? (/-/.test(g) ? 'После дефиса — номер группы из 3–4 цифр, например 1ИСИП-126' : 'Не хватает дефиса и номера группы: 1ИСИП-126')
        : 'Группа начинается с номера курса (1–6), например 1ИСИП-126';
      return err;
    },
    computeId: computeId, normGroup: normGroup, Vault: Vault,
  };
  window.ItcStudent = Student;

  // ---------- общий full-screen слой ----------
  function screen(html, cls) {
    var s = el('<section class="itc-ob ' + (cls || '') + '" role="dialog" aria-modal="true">' + html + '</section>');
    document.body.appendChild(s); document.documentElement.classList.add('itc-ob-open');
    requestAnimationFrame(function () { s.classList.add('in'); });
    s.close = function () { s.classList.remove('in'); s.classList.add('out'); document.documentElement.classList.remove('itc-ob-open'); setTimeout(function () { s.remove(); }, 260); };
    var f = s.querySelector('input'); if (f) setTimeout(function () { f.focus({ preventScroll: true }); }, 300);
    return s;
  }
  var ICON = '<img class="itc-ob-icon" src="/icons/splash-fg.png" alt="" width="96" height="96">';
  function dots(n, of) { var h = '<div class="itc-ob-dots" aria-label="Шаг ' + n + ' из ' + of + '">'; for (var i = 1; i <= of; i++) h += '<i' + (i === n ? ' class="on"' : '') + '></i>'; return h + '</div>'; }

  function roleScreen() {
    var L = window.ITC_CHANNEL === 'l';
    var s = screen('<div class="itc-ob-card">' + ICON + '<h1>ИТС Кружки</h1><p class="itc-ob-lead">Как вы будете пользоваться приложением? Роль можно сменить в Настройках.</p>' +
      '<button type="button" class="itc-ob-primary" data-role="student">Я студент</button>' +
      '<button type="button" class="itc-ob-secondary" data-role="teacher">Я преподаю</button>' +
      '<button type="button" class="itc-ob-secondary" data-role="admin">Сотрудник (вход в админку)</button>' +
      (L ? '<button type="button" class="itc-ob-link" data-role="demo-admin">Демо: войти как администратор</button>' : '') +
      '<button type="button" class="itc-ob-guest" data-role="guest">Продолжить как гость</button></div>' +
      '<footer class="itc-ob-foot"><span>' + (window.ITC_VERSION || '') + '</span><span>Made by ИТС КИПФИН</span></footer>', 'itc-ob-role');
    s.addEventListener('click', async function (e) {
      var b = e.target.closest('[data-role]'); if (!b) return; Haptics.tap();
      var r = b.getAttribute('data-role');
      var cur = Session.role();
      if (cur && cur !== 'guest' && cur !== r && !(r === 'demo-admin' && cur === 'admin')) await Session.logout(); // одна роль за раз
      s.close();
      if (r === 'student') { var st = await Student.load(); if (st) { Session.set('student', [st.profile.first, st.profile.last].join(' ')); location.href = '/'; } else profileScreen({ onboarding: true }); }
      else if (r === 'teacher') teacherLogin();
      else if (r === 'admin') location.href = '/admin/login.html';
      else if (r === 'demo-admin') location.href = '/admin/login.html?demo=1';
      else { Session.set('guest'); if (/^\/admin\//.test(location.pathname)) location.href = '/'; }
    });
  }

  function profileScreen(opt) {
    opt = opt || {};
    Student.load().then(function (cur) {
      var p = (cur && cur.profile) || {};
      var s = screen('<form class="itc-ob-card" novalidate>' + (opt.onboarding ? dots(1, 2) : '') + ICON +
        '<h1>' + (opt.onboarding ? 'Профиль студента' : 'Профиль') + '</h1>' +
        '<p class="itc-ob-lead">ФИО и группа хранятся только на этом телефоне в зашифрованном виде. На сервер уходит лишь анонимный ID.</p>' +
        field('last', 'Фамилия', p.last, 'family-name') + field('first', 'Имя', p.first, 'given-name') + field('middle', 'Отчество', p.noMiddle ? '' : p.middle, 'additional-name') +
        field('group', 'Группа', p.group, 'off', 'Курс, специальность и номер: 1ИСИП-126') +
        '<button type="submit" class="itc-ob-primary">Продолжить</button>' +
        (opt.onboarding ? '<button type="button" class="itc-ob-link" data-restore>У меня есть резервный код</button>' : '<button type="button" class="itc-ob-link" data-cancel>Отмена</button>') + '</form>');
      var f = s.querySelector('form'), mid = f.elements.middle;
      f.elements.group.addEventListener('input', function () { var c = this.selectionStart; this.value = this.value.toUpperCase().replace(/\s+/g, '').replace(/^(\d[А-ЯЁ]+)(\d)/, '$1-$2'); this.setSelectionRange(c, c); });
      s.addEventListener('click', function (e) {
        if (e.target.closest('[data-cancel]')) s.close();
        if (e.target.closest('[data-restore]')) { s.close(); restoreScreen(); }
      });
      f.addEventListener('submit', async function (e) {
        e.preventDefault();
        var np = { last: f.elements.last.value.trim(), first: f.elements.first.value.trim(), middle: mid.value.trim(), noMiddle: !mid.value.trim(), group: normGroup(f.elements.group.value) };
        var err = Student.validate(np); showErrors(f, err);
        if (Object.keys(err).length) { Haptics.error(); return; }
        var oldId = cur && cur.id;
        var st = await Student.save(np, opt.secret);
        Haptics.success(); s.close();
        if (opt.onboarding) idScreen(st, true);
        else toast(oldId && oldId !== st.id ? 'Профиль сохранён. ID изменился: ' + st.id.slice(0, 9) + '…' : 'Профиль сохранён');
      });
    });
  }
  function field(name, label, val, ac, hint) {
    return '<label class="itc-ob-field"><span>' + label + '</span><input name="' + name + '" value="' + esc(val || '') + '" autocomplete="' + ac + '" maxlength="60"' +
      (name === 'group' ? ' autocapitalize="characters" placeholder="1ИСИП-126"' : name === 'middle' ? ' autocapitalize="words" placeholder="необязательно"' : ' autocapitalize="words"') + '>' +
      (hint ? '<small class="itc-ob-hint">' + hint + '</small>' : '') + '<small class="itc-ob-err" data-err="' + name + '" role="alert"></small></label>';
  }
  function showErrors(f, err) {
    f.querySelectorAll('[data-err]').forEach(function (x) { var k = x.getAttribute('data-err'); x.textContent = err[k] || ''; f.elements[k].setAttribute('aria-invalid', String(!!err[k])); });
    var first = f.querySelector('[aria-invalid="true"]'); if (first) first.focus();
  }
  function idBlock(st) {
    return '<div class="itc-id"><span class="itc-id-label">Ваш ID</span><code class="itc-id-code" data-id>' + st.id + '</code>' +
      '<button type="button" class="itc-ob-secondary" data-copy="' + st.id + '">Скопировать ID</button></div>';
  }
  function bindCopy(root) {
    root.addEventListener('click', function (e) {
      var b = e.target.closest('[data-copy]'); if (!b) return;
      var t = b.getAttribute('data-copy'), lbl = b.textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { b.textContent = 'Скопировано ✓'; Haptics.tap(); }, function () { b.textContent = 'Не удалось — выделите вручную'; })
        .then(function () { setTimeout(function () { b.textContent = lbl; }, 1600); });
    });
  }
  function idScreen(st, onboarding) {
    var s = screen('<div class="itc-ob-card">' + (onboarding ? dots(2, 2) : '') + ICON + '<h1>Готово</h1>' + idBlock(st) +
      '<p class="itc-ob-lead">Этот ID вы показываете при отметке. По нему нельзя узнать ваше имя. Сохраните резервный код — без него на новом телефоне будет новый ID.</p>' +
      '<button type="button" class="itc-ob-secondary" data-backup>Резервный код</button>' +
      '<button type="button" class="itc-ob-primary" data-done>Продолжить</button></div>');
    bindCopy(s);
    s.addEventListener('click', function (e) {
      if (e.target.closest('[data-backup]')) backupScreen(st);
      if (e.target.closest('[data-done]')) { s.close(); if (onboarding && window.ItcOnboarding && window.ItcOnboarding.next) window.ItcOnboarding.next(); }
    });
  }
  function qrSvg(text) {
    return new Promise(function (ok) {
      function make() { var q = window.qrcode(0, 'M'); q.addData(text); q.make(); ok(q.createSvgTag({ cellSize: 6, margin: 2, scalable: true })); }
      if (window.qrcode) return make();
      var sc = document.createElement('script'); sc.src = '/js/vendor/qrcode.js'; sc.onload = make; sc.onerror = function () { ok(''); }; document.head.appendChild(sc);
    });
  }
  function backupScreen(st) {
    var code = Student.backupCode(st.secret);
    var s = screen('<div class="itc-ob-card"><h1>Резервный код</h1><p class="itc-ob-lead">Это ключ вашего ID. Не показывайте его другим: по нему можно отмечаться от вашего имени. ' +
      'На новом телефоне: «Я студент» → «У меня есть резервный код» и те же ФИО и группа.</p><div class="itc-ob-qr" data-qr></div>' +
      '<code class="itc-id-code itc-backup">' + code + '</code><button type="button" class="itc-ob-secondary" data-copy="' + code + '">Скопировать код</button>' +
      '<button type="button" class="itc-ob-primary" data-close>Я сохранил(а)</button></div>');
    bindCopy(s); qrSvg('itc-backup1:' + code).then(function (svg) { s.querySelector('[data-qr]').innerHTML = svg; });
    s.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) s.close(); });
  }
  function restoreScreen() {
    var s = screen('<form class="itc-ob-card" novalidate>' + ICON + '<h1>Восстановление</h1><p class="itc-ob-lead">Вставьте резервный код (R-…). Затем укажите те же ФИО и группу — получится прежний ID.</p>' +
      '<label class="itc-ob-field"><span>Резервный код</span><textarea name="code" rows="3" autocapitalize="characters" spellcheck="false"></textarea><small class="itc-ob-err" data-err="code" role="alert"></small></label>' +
      '<button type="submit" class="itc-ob-primary">Продолжить</button><button type="button" class="itc-ob-link" data-cancel>Назад</button></form>');
    var f = s.querySelector('form');
    s.addEventListener('click', function (e) { if (e.target.closest('[data-cancel]')) { s.close(); profileScreen({ onboarding: true }); } });
    f.addEventListener('submit', function (e) {
      e.preventDefault(); var sec = Student.parseBackup(f.elements.code.value);
      if (!sec) { showErrors(f, { code: 'Код не распознан: 13 групп по 4 символа после R-' }); Haptics.error(); return; }
      s.close(); profileScreen({ onboarding: true, secret: sec });
    });
  }

  // ---------- «Мои посещения» (только со своего устройства) ----------
  async function myVisits() {
    var st = await Student.load(); if (!st) { profileScreen({ onboarding: true }); return; }
    var s = screen('<div class="itc-ob-card itc-ob-wide"><h1>Мои посещения</h1>' + idBlock(st) + '<div data-list class="itc-visits"><p class="itc-ob-lead">Загрузка…</p></div>' +
      '<p class="itc-ob-hint">Данные о посещениях хранятся 21 день.</p><button type="button" class="itc-ob-primary" data-close>Закрыть</button></div>');
    bindCopy(s); s.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) s.close(); });
    var box = s.querySelector('[data-list]');
    try {
      var r = await fetch('/api/attendance/mine', { headers: { 'X-Student-Id': st.id, 'X-Device-Token': st.device } });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(humanError(r.status, j.detail));
      var by = {}; j.items.forEach(function (x) { by[x.club_name] = (by[x.club_name] || 0) + 1; });
      var sum = j.items.length ? '<div class="itc-vstat"><div><b>' + j.items.length + '</b><small>посещений за 3 недели</small></div>' + Object.keys(by).sort(function (a, b) { return by[b] - by[a]; }).map(function (k) {
        return '<div><b>' + by[k] + '</b><small>' + esc(k) + '</small></div>'; }).join('') + '</div>' : '';
      box.innerHTML = j.items.length ? sum + '<ul>' + j.items.map(function (x) {
        return '<li><b>' + esc(x.club_name) + '</b><span>' + x.date.split('-').reverse().join('.') + ', ' + esc(x.start_time) + '–' + esc(x.end_time) + (x.method === 'manual' ? ' · вручную' : '') + '</span></li>'; }).join('') + '</ul>'
        : '<p class="itc-ob-lead">За 21 день отметок нет.</p>';
    } catch (e) { box.innerHTML = '<p class="itc-ob-err">' + esc(clean(e.message) || HUMAN[0]) + '</p>'; }
  }

  // ---------- преподаватель ----------
  var Teacher = {
    session: function () { try { var v = JSON.parse(LS.getItem(TSES)); return v && v.exp > Date.now() ? v : null; } catch (e) { return null; } },
    login: async function (token) {
      var r = await fetch('/api/teacher/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: token }) });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(r.status === 422 ? 'Идентификатор выглядит так: T-XXXX-XXXX-…' : humanError(r.status, j.detail));
      LS.setItem(TSES, JSON.stringify({ tok: j.access_token, exp: Date.now() + (j.expires_in - 60) * 1000, name: j.teacher.name }));
      await Vault.set(Object.assign({}, (await Vault.get()) || {}, { teacherToken: token })); // для тихого повторного входа
      Session.set('teacher', j.teacher.name, 30 * 864e5); return j;
    },
    // перенос аккаунта: одноразовый QR из админки → новый постоянный идентификатор сохраняется в Keystore
    transfer: async function (code) {
      var r = await fetch('/api/teacher/transfer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code }) });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(r.status === 422 ? 'Это не QR переноса. Попросите администратора открыть «QR переноса».' : humanError(r.status, j.detail));
      LS.setItem(TSES, JSON.stringify({ tok: j.access_token, exp: Date.now() + (j.expires_in - 60) * 1000, name: j.teacher.name }));
      await Vault.set(Object.assign({}, (await Vault.get()) || {}, { teacherToken: j.token }));
      Session.set('teacher', j.teacher.name, 30 * 864e5); return j;
    },
    api: async function (path, opt) {
      var s = Teacher.session();
      if (!s) { var v = await Vault.get(); if (v && v.teacherToken) { await Teacher.login(v.teacherToken); s = Teacher.session(); } }
      if (!s) throw Object.assign(new Error('Войдите по идентификатору преподавателя'), { status: 401 });
      opt = opt || {}; opt.headers = Object.assign({ Authorization: 'Bearer ' + s.tok }, opt.body ? { 'Content-Type': 'application/json' } : {}, opt.headers || {});
      var r = await fetch(path, opt);
      if (r.status === 204) return null;
      var j = await r.json().catch(function () { return {}; });
      if (r.status === 401) LS.removeItem(TSES);
      if (!r.ok) throw Object.assign(new Error(humanError(r.status, j.detail)), { status: r.status });
      return j;
    },
    logout: async function () { LS.removeItem(TSES); var v = await Vault.get(); if (v) { delete v.teacherToken; if (v.secret) await Vault.set(v); else await Vault.wipe(); } Session.set('guest'); },
  };
  window.ItcTeacher = Teacher;

  // ---------- офлайн-очередь отметок (t100) ----------
  // Без сети отметка сохраняется с реальным временем сканирования; сервер проверяет, что QR был действителен
  // именно в тот момент и попадал в окно отметки (не позже 6 ч). Отправляем при появлении сети.
  var QKEY = 'itc.checkinQueue';
  var Queue = {
    list: function () { try { return JSON.parse(LS.getItem(QKEY)) || []; } catch (e) { return []; } },
    save: function (a) { if (a.length) LS.setItem(QKEY, JSON.stringify(a)); else LS.removeItem(QKEY); document.dispatchEvent(new CustomEvent('itc:queue', { detail: a })); },
    add: function (item) { var a = Queue.list(); a.push(item); Queue.save(a); },
    _busy: false,
    flush: async function () {
      if (Queue._busy || !navigator.onLine) return []; var a = Queue.list(); if (!a.length) return [];
      Queue._busy = true; var keep = [], done = [];
      for (var i = 0; i < a.length; i++) {
        var it = a[i];
        try {
          var r = await fetch('/api/attendance/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(it.body) });
          var j = await r.json().catch(function () { return {}; });
          if (r.status === 201) done.push({ ok: true, club: j.club_name, t: j.start_time + '–' + j.end_time });
          else if (r.status >= 500 || r.status === 429) keep.push(it);
          else done.push({ ok: /Уже отмечен/.test(j.detail || ''), club: it.club || '', err: humanError(r.status, j.detail) });
        } catch (e) { keep.push(it); }
      }
      Queue.save(keep); Queue._busy = false;
      done.forEach(function (d) { toast(d.ok ? '✓ Отметка из очереди засчитана' + (d.club ? ': ' + d.club : '') : 'Отметка из очереди не засчитана: ' + d.err); });
      if (done.some(function (d) { return d.ok; })) Haptics.success();
      return done;
    },
  };
  window.ItcQueue = Queue;
  if (typeof window.addEventListener === 'function' && typeof fetch === 'function' && typeof navigator !== 'undefined') {
    window.addEventListener('online', function () { Queue.flush(); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) Queue.flush(); });
    setTimeout(function () { Queue.flush(); }, 1500);
  }

  function teacherLogin() {
    var s = screen('<form class="itc-ob-card" novalidate>' + ICON + '<h1>Вход преподавателя</h1><p class="itc-ob-lead">Вставьте идентификатор, который выдал администратор (T-…).</p>' +
      '<label class="itc-ob-field"><span>Идентификатор</span><input name="tok" autocapitalize="characters" autocomplete="off" spellcheck="false" placeholder="T-XXXX-XXXX-…"><small class="itc-ob-err" data-err="tok" role="alert"></small></label>' +
      '<button type="submit" class="itc-ob-primary">Войти</button>' +
      (P.ItcScanner ? '<button type="button" class="itc-ob-secondary" data-transfer>Сканировать QR переноса</button>' : '') +
      '<button type="button" class="itc-ob-link" data-cancel>Назад</button></form>');
    var f = s.querySelector('form');
    s.addEventListener('click', async function (e) {
      if (!e.target.closest('[data-transfer]')) return;
      try {
        var r = await P.ItcScanner.scan({ hint: 'Наведите на QR переноса из админки' });
        if (!r || r.cancelled || !r.text) return;
        if (r.text.indexOf('itc-tx1.') !== 0) throw new Error('Это не QR переноса. Попросите администратора открыть «QR переноса».');
        await Teacher.transfer(r.text); Haptics.success(); s.close(); toast('Аккаунт перенесён на этот телефон'); teacherHome();
      } catch (x) { showErrors(f, { tok: clean(x.message) || 'Не удалось открыть камеру' }); Haptics.error(); }
    });
    s.addEventListener('click', function (e) { if (e.target.closest('[data-cancel]')) { s.close(); if (!Student.role()) roleScreen(); } });
    f.addEventListener('submit', async function (e) {
      e.preventDefault(); var b = f.querySelector('[type=submit]'); b.disabled = true;
      try { await Teacher.login(f.elements.tok.value.trim()); Haptics.success(); s.close(); teacherHome(); }
      catch (x) { showErrors(f, { tok: x.message }); Haptics.error(); }
      finally { b.disabled = false; }
    });
  }
  var WD = ['', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
  function mskNow() { var d = new Date(Date.now() + (new Date().getTimezoneOffset() + 180) * 60000); return d; }
  function isoDate(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  async function teacherHome() {
    var s = screen('<div class="itc-ob-card itc-ob-wide"><h1>Мои кружки</h1><p class="itc-ob-lead" data-name></p><div data-list class="itc-tlist">Загрузка…</div>' +
      '<button type="button" class="itc-ob-secondary" data-close>К расписанию</button><button type="button" class="itc-ob-link" data-logout>Выйти из режима преподавателя</button></div>', 'itc-ob-scroll');
    s.addEventListener('click', async function (e) {
      if (e.target.closest('[data-close]')) s.close();
      if (e.target.closest('[data-logout]')) { await Teacher.logout(); s.close(); toast('Вы вышли из режима преподавателя'); }
      var b = e.target.closest('[data-session]'); if (b) { Haptics.tap(); sessionScreen(JSON.parse(b.getAttribute('data-session'))); }
    });
    try {
      var me = await Teacher.api('/api/teacher/me'); var now = mskNow(), wd = (now.getDay() || 7);
      s.querySelector('[data-name]').textContent = me.name + ' · только просмотр и отметка посещаемости';
      var list = await Teacher.api('/api/teacher/occurrences?date=' + isoDate(now) + '&days=7');
      s.querySelector('[data-list]').innerHTML = list.length ? list.map(function (x) {
        var d = new Date(x.date + 'T12:00:00'), today = x.date === isoDate(now);
        return '<button type="button" class="itc-tsession' + (today ? ' is-today' : '') + '" data-session=\'' + esc(JSON.stringify({ id: x.session_id, date: x.date, original_date: x.original_date, club: x.club_name, t: x.start_time + '–' + x.end_time, room: x.room_name })) + '\'>' +
          '<span class="itc-tsession-time">' + (today ? 'Сегодня' : WD[d.getDay() || 7]) + '<b>' + x.start_time + '</b></span><span class="itc-tsession-main"><b>' + esc(x.club_name) + '</b><small>' + esc(x.room_name) + ' · ' + x.start_time + '–' + x.end_time + (x.status === 'moved' ? ' · перенос' : '') + '</small></span></button>';
      }).join('') : '<p class="itc-ob-lead">За вами пока нет кружков. Обратитесь к администратору.</p>';
    } catch (x) { s.querySelector('[data-list]').innerHTML = '<p class="itc-ob-err">' + esc(x.message) + '</p>'; if (x.status === 401) { s.close(); teacherLogin(); } }
  }
  function mmss(n) { n = Math.max(0, n); return Math.floor(n / 60) + ':' + String(n % 60).padStart(2, '0'); }
  function hm(t) { return new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }); }
  function sessionScreen(ss) {
    var s = screen('<div class="itc-ob-card itc-ob-wide itc-qrscreen"><h1>' + esc(ss.club) + '</h1><p class="itc-ob-lead">' + ss.date.split('-').reverse().join('.') + ' · ' + esc(ss.t) + (ss.room ? ' · ' + esc(ss.room) : '') + '</p>' +
      '<div class="itc-qrstage" data-stage aria-live="polite"></div><h2>Отметились: <b data-count>0</b></h2><ol class="itc-live" data-live></ol>' +
      '<form class="itc-manual" data-manual><input name="sid" placeholder="S-XXXX-XXXX-…" autocapitalize="characters" autocomplete="off" spellcheck="false" aria-label="ID студента"><button type="submit" class="itc-ob-secondary">Отметить по ID</button></form>' +
      '<button type="button" class="itc-ob-primary" data-close>Закрыть</button></div>', 'itc-ob-scroll');
    var stage = s.querySelector('[data-stage]'), live = s.querySelector('[data-live]'), cnt = s.querySelector('[data-count]');
    var timer = 0, poll = 0, since = 0, alive = true, first = true;
    function stop() { alive = false; clearTimeout(timer); clearInterval(poll); }
    s.addEventListener('click', async function (e) {
      if (e.target.closest('[data-close]')) { stop(); s.close(); return; }
      var del = e.target.closest('[data-del]');
      if (del && confirm('Удалить отметку ' + del.getAttribute('data-sid') + '?')) {
        try { await Teacher.api('/api/teacher/attendance/' + del.getAttribute('data-del'), { method: 'DELETE' }); del.closest('li').remove(); cnt.textContent = String(Math.max(0, +cnt.textContent - 1)); Haptics.tap(); }
        catch (x) { toast(x.message); }
      }
    });
    s.querySelector('[data-manual]').addEventListener('submit', async function (e) {
      e.preventDefault(); var inp = this.elements.sid;
      try { await Teacher.api('/api/teacher/attendance/manual', { method: 'POST', body: JSON.stringify({ session_id: ss.id, date: ss.date, original_date: ss.original_date, student_id: inp.value }) }); inp.value = ''; Haptics.success(); pull(); }
      catch (x) { Haptics.error(); toast(x.message); }
    });
    async function tick() {
      if (!alive) return;
      var r; try { r = await Teacher.api('/api/teacher/attendance/qr', { method: 'POST', body: JSON.stringify({ session_id: ss.id, date: ss.date, original_date: ss.original_date }) }); }
      catch (x) { stage.innerHTML = '<p class="itc-ob-err">' + esc(x.message) + '</p>'; timer = setTimeout(tick, 5000); return; }
      if (!alive) return;
      if (r.state === 'early') {
        var left = r.opens_in;
        stage.innerHTML = '<div class="itc-qr-wait"><b>QR ещё не готов</b><span>откроется за 10 с до начала через <time data-cd>' + mmss(left) + '</time></span></div>';
        var cd = stage.querySelector('[data-cd]');
        (function step() { if (!alive) return; left -= 1; cd.textContent = mmss(left); if (left <= 0) tick(); else timer = setTimeout(step, 1000); })();
        return;
      }
      if (r.state === 'closed') { stage.innerHTML = '<div class="itc-qr-wait"><b>Отметка закрыта</b><span>QR выдавался первые ' + r.window_min + ' мин. Вручную по ID — до ' + hm(r.manual_until) + '.</span></div>'; return; }
      var svg = await qrSvg(r.token);
      if (!alive) return;
      stage.innerHTML = '<div class="itc-qr-code">' + svg + '</div><p class="itc-ob-hint">Код меняется каждые ' + r.rotate + ' с · приём ещё ' + Math.ceil(r.closes_in / 60) + ' мин' + (r.demo_free_window ? ' · демо: окно не ограничено' : '') + '</p>';
      timer = setTimeout(tick, Math.min(r.rotate, Math.max(1, r.closes_in + 1)) * 1000);
    }
    async function pull() {
      if (!alive) return;
      try {
        var r = await Teacher.api('/api/teacher/attendance?session_id=' + ss.id + '&date=' + ss.date + (ss.original_date ? '&original_date=' + ss.original_date : ''));
        if (!alive) return;
        var ids = new Set(r.items.map(function (it) { return String(it.id); }));
        live.querySelectorAll('[data-del]').forEach(function (b) { if (!ids.has(b.getAttribute('data-del'))) b.closest('li').remove(); });
        if (cnt.textContent !== String(r.count) && !first) { cnt.classList.remove('itc-bump'); void cnt.offsetWidth; cnt.classList.add('itc-bump'); }
        cnt.textContent = String(r.count);
        // живой счётчик: короткая вибрация на каждую новую отметку (без звука), не чаще раза в 120 мс
        r.items.forEach(function (it) {
          if (live.querySelector('[data-del="' + it.id + '"]')) return;
          if (!first) Haptics.success();
          since = Math.max(since, it.id);
          live.insertAdjacentHTML('afterbegin', '<li class="' + (first ? '' : 'new') + '"><code title="' + esc(it.student_id) + '">' + esc(it.short) + '</code><span>' + (it.method === 'manual' ? 'вручную' : 'отметился') + ', ' + hm(it.at) + '</span>' +
            '<button type="button" class="itc-del" data-del="' + it.id + '" data-sid="' + esc(it.short) + '" aria-label="Удалить отметку">Удалить</button></li>');
        });
        first = false;
      } catch (x) { /* следующий опрос */ }
    }
    tick(); pull(); poll = setInterval(pull, 2000);
    // экран не гаснет, пока показан QR (если плагин доступен)
    try { if (P.KeepAwake) P.KeepAwake.keepAwake(); } catch (e) { /* нет */ }
  }

  async function openProfile() {
    var st = await Student.load(); if (!st) { profileScreen({ onboarding: true }); return; }
    var p = st.profile;
    var s = screen('<div class="itc-ob-card itc-ob-wide"><h1>Профиль</h1><p class="itc-ob-lead">' + esc([p.last, p.first, p.noMiddle ? '' : p.middle].join(' ')) + ' · ' + esc(p.group) + '</p>' + idBlock(st) +
      '<p class="itc-ob-hint">Хранится только на этом телефоне, зашифровано' + (Vault.native() ? ' (Android Keystore)' : '') + '. Данные о посещениях хранятся 21 день.</p>' +
      '<button type="button" class="itc-ob-secondary" data-edit>Изменить ФИО или группу</button><button type="button" class="itc-ob-secondary" data-backup>Резервный код</button>' +
      '<button type="button" class="itc-ob-secondary" data-visits>Мои посещения</button><button type="button" class="itc-ob-primary" data-close>Готово</button>' +
      '<button type="button" class="itc-ob-link itc-danger" data-wipe>Удалить профиль с телефона</button></div>', 'itc-ob-scroll');
    bindCopy(s);
    s.addEventListener('click', async function (e) {
      if (e.target.closest('[data-close]')) s.close();
      if (e.target.closest('[data-edit]')) { s.close(); profileScreen({}); }
      if (e.target.closest('[data-backup]')) backupScreen(st);
      if (e.target.closest('[data-visits]')) { s.close(); myVisits(); }
      if (e.target.closest('[data-wipe]') && confirm('Удалить профиль и ключ ID с телефона? Без резервного кода прежний ID не восстановить.')) { await Vault.wipe(); cache = null; Session.set('guest'); s.close(); toast('Профиль удалён'); }
    });
  }
  Student.openProfile = openProfile; Student.myVisits = myVisits; Student.roleScreen = roleScreen; Student.profileScreen = profileScreen; Teacher.home = teacherHome; Teacher.loginScreen = teacherLogin;

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
    if (r === 'guest' || !r) acc = '<div class="itc-acc"><div class="itc-acc-ava" aria-hidden="true">?</div><div class="itc-acc-tx"><b>Вы не вошли</b><small>' +
      (ses.expired ? 'Срок входа истёк — войдите снова' : 'Студенту — отметки на занятиях, преподавателю — QR и список группы') + '</small></div></div>' +
      '<button type="button" class="itc-ob-primary itc-acc-btn" data-act="login">Войти</button>';
    else acc = '<div class="itc-acc"><div class="itc-acc-ava" aria-hidden="true">' + esc((ses.name || ROLES[r]).trim().charAt(0).toUpperCase()) + '</div><div class="itc-acc-tx"><b>' + esc(ses.name || ROLES[r]) + '</b><small>' + ROLES[r] + '</small></div></div>' +
      (r === 'student' ? row('Профиль', { act: 'profile', sub: 'ФИО, группа, ID, резервный код' }) + row('Мои посещения', { act: 'visits' }) : '') +
      (r === 'teacher' ? row('Мои занятия', { act: 'thome', sub: 'QR для отметки и список группы' }) : '') +
      (r === 'admin' ? row('Админка', { act: 'admin' }) : '') +
      row('Сменить роль', { act: 'login' }) + row('Выйти', { act: 'logout', danger: true });
    var s = screen('<div class="itc-set">' +
      '<header class="itc-set-head"><button type="button" class="itc-set-back" data-act="close" aria-label="Назад"><svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><h1>Настройки</h1></header>' +
      '<div class="itc-set-body">' +
      '<h2>Аккаунт</h2><div class="itc-group">' + acc + '</div>' +
      '<h2>Оформление</h2><div class="itc-group"><div class="itc-field"><span>Тема</span>' + seg('theme', [['system', 'Системная'], ['light', 'Светлая'], ['dark', 'Тёмная']], pr.theme) + '</div>' +
      '<div class="itc-field"><span>Размер текста</span>' + seg('textSize', [['normal', 'Обычный'], ['large', 'Крупный'], ['xlarge', 'Очень крупный']], pr.textSize) + '</div>' +
      '<div class="itc-field"><span>Акцентный цвет</span><div class="itc-swatches" role="radiogroup" data-seg="accent">' + ACC.map(function (a) {
        return '<button type="button" role="radio" class="itc-sw" data-accent="' + a[0] + '" data-v="' + a[0] + '" aria-label="' + a[1] + '" aria-checked="' + (a[0] === pr.accent) + '"></button>'; }).join('') + '</div></div></div>' +
      '<h2>Уведомления</h2><div class="itc-group"><label class="itc-row itc-row-sw"><span class="itc-row-tx"><span>Вибрация</span><small>Короткий отклик на нажатия и отметки</small></span><input type="checkbox" role="switch" class="itc-switch" data-haptics' + (Haptics.on() ? ' checked' : '') + '></label><div data-ext="notify"></div></div>' +
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
        if (!confirm(r === 'student' ? 'Выйти из роли студента? Профиль останется зашифрованным на телефоне — вернуться можно через «Войти».' : 'Выйти из аккаунта?')) return;
        await Session.logout(); s.close(); toast('Вы вышли'); if (/^\/admin\//.test(location.pathname) || r !== 'student') location.href = '/'; return;
      }
      s.close();
      if (a === 'login') roleScreen();
      else if (a === 'profile') openProfile();
      else if (a === 'visits') myVisits();
      else if (a === 'thome') teacherHome();
      else if (a === 'admin') location.href = '/admin/index.html';
      else if (a === 'update') { if (window.ItcAppUpdate) window.ItcAppUpdate.check({ manual: true }); else toast('Обновления проверяются только в приложении'); }
    });
  }
  window.ItcSettings = { open: settingsScreen, row: row };

  // ---------- t99: запуск и разделение ролей ----------
  // admin → админка; teacher → «Мои занятия»; student/guest → расписание. Не-админ в /admin/* → вход для сотрудников.
  function roleHomeChip() {
    var r = Session.role(); if (r !== 'teacher' && r !== 'admin') return;
    var h = document.querySelector('body.campus-page:not(.admin-page) > .campus-header'); if (!h || h.querySelector('.itc-home-chip')) return;
    var a = el('<a class="itc-home-chip" href="' + (r === 'admin' ? '/admin/index.html' : '/?teacher=1') + '">' + (r === 'admin' ? 'Админка' : 'Мои занятия') + '</a>');
    var g = h.querySelector('.app-gear'); if (g) h.insertBefore(a, g); else h.appendChild(a);
  }
  function boot() {
    var p = location.pathname, q = new URLSearchParams(location.search), r = Session.role();
    var NATIVE = window.Capacitor && Capacitor.isNativePlatform && Capacitor.isNativePlatform();
    if (/^\/admin\//.test(p) && !/login/.test(p)) { if (NATIVE && r !== 'admin') location.replace('/admin/login.html'); return; }
    if (/^\/admin\//.test(p) || /qr\.html$/.test(p) || /settings\.html$/.test(p)) return;
    var home = p === '/' || /\/index\.html$/.test(p);
    if (home && !r) { setTimeout(roleScreen, window.ItcSplash ? 700 : 0); return; }
    var cold = home && !sessionStorage.getItem('itc.launched') && !q.get('from'); sessionStorage.setItem('itc.launched', '1');
    if (cold && r === 'admin') { location.replace('/admin/index.html'); return; }
    if ((cold && r === 'teacher') || (q.get('teacher') === '1' && r === 'teacher')) teacherHome();
    roleHomeChip(); setTimeout(roleHomeChip, 400);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
