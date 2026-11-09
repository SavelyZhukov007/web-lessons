/* PWA-часть (phase 2 D): web push для «Моих кружков», значок на иконке (Badging API), шторка «Уведомления»,
 * размер текста iOS (Dynamic Type). Работает только при window.ItcPwa (ставит pwa-standalone.js в режиме standalone). */
(function () {
  'use strict';
  if (window.ItcPwa !== true) return;
  var doc = document, root = doc.documentElement, LS = window.localStorage;
  var F = window.ItcFeatures; // native-features.js
  if (!F) return;
  var PUSH_KEY = 'itc.pwa.push', SUBS_KEY = 'itc.pwa.pushClubs', SEEN_KEY = 'itc.pwa.seen', ASKED_KEY = 'itc.pwa.asked';
  var PUSH_OPTIONS = { cancellations: 'Отмены занятий', moves: 'Переносы занятий', announcements: 'Объявления от администрации' };
  var pushFields = Object.keys(PUSH_OPTIONS);
  function preference(field) { return LS.getItem('itc.pwa.' + field) !== '0'; }
  function setPreference(field, value) { LS.setItem('itc.pwa.' + field, value ? '1' : '0'); }
  var ios = root.classList.contains('is-pwa-ios');
  function jget(k, d) { try { var v = JSON.parse(LS.getItem(k)); return v == null ? d : v; } catch (e) { return d; } }
  function jset(k, v) { try { LS.setItem(k, JSON.stringify(v)); } catch (e) { /* полон */ } }
  var toast = F.toast, el = F.el, baseFetch = F.baseFetch;

  // pwa.css — последним, после native-shell.css (тот переезжает в конец <head> на DOMContentLoaded)
  function addCss() {
    var l = doc.querySelector('link[data-pwa-css]');
    if (!l) { l = doc.createElement('link'); l.rel = 'stylesheet'; l.href = '/pwa/pwa.css'; l.setAttribute('data-pwa-css', ''); }
    doc.head.appendChild(l);
  }
  addCss();
  doc.addEventListener('DOMContentLoaded', addCss);

  // ---------- iOS: системный размер текста (Dynamic Type) -> --text-scale, если пользователь не выбрал размер сам ----------
  function dynamicType() {
    if (!ios || root.getAttribute('data-text-size') !== 'normal' || !doc.body) return;
    var p = doc.createElement('span'); p.style.cssText = 'position:absolute;visibility:hidden;font:-apple-system-body'; doc.body.appendChild(p);
    var px = parseFloat(getComputedStyle(p).fontSize); p.remove();
    if (px && px !== 17) root.style.setProperty('--text-scale', String(Math.min(2, Math.max(0.85, px / 17)).toFixed(3)));
  }

  // ---------- web push ----------
  function env() {
    return { secure: window.isSecureContext === true, sw: 'serviceWorker' in navigator, push: 'PushManager' in window,
             notif: 'Notification' in window, perm: 'Notification' in window ? Notification.permission : 'unsupported' };
  }
  function availability() {
    var e = env();
    if (!e.secure) return { ok: false, msg: 'Уведомления работают только по HTTPS.' };
    if (!e.sw || !e.push || !e.notif) return { ok: false, msg: ios ? 'Для уведомлений нужен iOS/iPadOS 16.4 или новее.' : 'Это устройство не поддерживает push-уведомления.' };
    if (e.perm === 'denied') return { ok: false, denied: true, msg: ios ? 'Уведомления запрещены: Настройки → Уведомления → «KipClub».' : 'Уведомления запрещены в настройках сайта/приложения.' };
    return { ok: true, msg: '' };
  }
  function enabled() { return LS.getItem(PUSH_KEY) === '1' && env().perm === 'granted'; }
  function api(path, body) {
    return baseFetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  }
  function b64(s) { var p = '='.repeat((4 - s.length % 4) % 4); var raw = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); }); }
  function reg() { return navigator.serviceWorker.getRegistration('/').then(function (r) { return r || navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function () { return navigator.serviceWorker.ready; }); }); }
  function subscription(create) {
    return reg().then(function (r) {
      return r.pushManager.getSubscription().then(function (s) {
        if (s || !create) return s;
        return api('/api/push/vapid-public-key').then(function (k) { return r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(k.publicKey) }); });
      });
    });
  }
  // Изменение состава кружков, настроек и отключение идут в порядке нажатий.
  var pushQueue = Promise.resolve();
  function queuePush(action) {
    var work = pushQueue.then(action);
    pushQueue = work.catch(function () {});
    return work;
  }
  function syncSubs() {
    return queuePush(function () {
      if (!enabled()) return null;
      return subscription(true).then(function (s) {
        var j = s.toJSON(), body = { endpoint: j.endpoint, keys: j.keys, club_ids: F.Follows.all() };
        pushFields.forEach(function (field) { body[field] = preference(field); });
        return api('/api/push/sync', body).then(function (status) { jset(SUBS_KEY, status.club_ids); return status; });
      });
    });
  }
  // ВАЖНО: Notification.requestPermission вызывается только отсюда — из обработчика нажатия пользователя
  function enableFromGesture() {
    var a = availability();
    if (!a.ok) { toast(a.msg); return Promise.resolve(false); }
    return Notification.requestPermission().then(function (p) {
      if (p !== 'granted') { LS.setItem(PUSH_KEY, '0'); toast(ios ? 'Без разрешения уведомления не придут. Включить: Настройки → Уведомления → «KipClub».' : 'Разрешение на уведомления не выдано.'); return false; }
      LS.setItem(PUSH_KEY, '1');
      return syncSubs().then(function () { toast('Уведомления включены на этом устройстве'); refreshBadge(); return true; },
        function () { LS.setItem(PUSH_KEY, '0'); toast('Не удалось включить уведомления. Проверьте соединение и повторите.'); return false; });
    });
  }
  function disable() {
    LS.setItem(PUSH_KEY, '0');
    return queuePush(function () {
      return subscription(false).then(function (s) {
        if (!s) return;
        return api('/api/push/unsubscribe', { endpoint: s.endpoint }).finally(function () { return s.unsubscribe(); });
      });
    }).then(function () { jset(SUBS_KEY, []); toast('Уведомления отключены'); }, function () {
      jset(SUBS_KEY, []); toast('Не удалось подтвердить отключение на сервере. Повторите при подключении.');
    });
  }

  // Звёздочка: подписки догоняют «Мои кружки»; разрешение не спрашиваем само — предлагаем кнопкой
  doc.addEventListener('itc:follows', function (e) {
    if (enabled()) { syncSubs().catch(function () { toast('Подписки пока не сохранены — повторим при подключении.'); }); return; }
    var a = availability();
    if (!a.ok || LS.getItem(PUSH_KEY) === '0' || !(e.detail || []).length || sessionStorage.getItem(ASKED_KEY)) return;
    sessionStorage.setItem(ASKED_KEY, '1');
    offer();
  });
  function offer() {
    var old = doc.getElementById('itc-push-offer'); if (old) old.remove();
    doc.querySelectorAll('.itc-toast').forEach(function (t) { t.remove(); }); // предложение заменяет тост «Добавлено»
    var bar = el('div', { id: 'itc-push-offer', class: 'itc-offer', role: 'status' },
      '<span>Сообщать об отменах и переносах «Моих кружков»?</span><button type="button" data-a="yes">Включить</button><button type="button" data-a="no" aria-label="Не сейчас">Не сейчас</button>');
    bar.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b) return;
      bar.remove();
      if (b.getAttribute('data-a') === 'yes') enableFromGesture(); else LS.setItem(PUSH_KEY, '0');
    });
    doc.body.appendChild(bar);
    setTimeout(function () { if (bar.isConnected) bar.remove(); }, 12000);
  }

  // ---------- шторка «Уведомления» (вместо «Напоминания и виджеты» APK) ----------
  function openSheet() {
    if (doc.getElementById('itc-sheet')) return;
    var a = availability(), on = enabled(), n = F.Follows.all().length;
    var opener = doc.activeElement;
    var wrap = el('div', { id: 'itc-sheet', class: 'itc-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'itc-sheet-title' });
    wrap.innerHTML = '<div class="itc-sheet-card">' +
      '<h2 id="itc-sheet-title">Уведомления</h2>' +
      '<p class="itc-muted">' + (n ? 'Изменения расписания для «Моих кружков» (' + n + ').' : 'Отметьте кружки звёздочкой, чтобы получать их отмены и переносы. Общие объявления доступны без избранного.') + '</p>' +
      '<label class="itc-row"><span>Пуш-уведомления на этом устройстве</span><input type="checkbox" id="itc-push"' + (on ? ' checked' : '') + (a.ok || on ? '' : ' disabled') + '></label>' +
      '<p id="itc-push-msg" class="itc-warn"' + (a.ok ? ' hidden' : '') + '>' + a.msg + '</p>' +
      '<h3>Какие уведомления получать</h3>' +
      pushFields.map(function (field) {
        return '<label class="itc-row"><span>' + PUSH_OPTIONS[field] + '</span><input type="checkbox" id="' + (field === 'announcements' ? 'itc-ann' : 'itc-' + field) +
          '" data-push-field="' + field + '"' + (preference(field) ? ' checked' : '') + (a.ok ? '' : ' disabled') + '></label>';
      }).join('') +
      '<p class="itc-muted small">' + (ios ? 'Звук и вибрация: Настройки iPhone → Уведомления → KipClub.' :
        'Звук и вибрация зависят от настроек браузера и телефона.') + '</p>' +
      '<label class="itc-row"><span>Значок с числом изменений на иконке</span><input type="checkbox" id="itc-badge"' + (LS.getItem('itc.pwa.badge') !== '0' ? ' checked' : '') + ('setAppBadge' in navigator ? '' : ' disabled') + '></label>' +
      ('setAppBadge' in navigator ? '' : '<p class="itc-muted small">Значок на иконке это устройство не поддерживает.</p>') +
      '<button type="button" class="itc-close">Готово</button></div>';
    doc.body.appendChild(wrap);
    var personalPanel;
    import('/js/schedule-notification-form.js').then(function(m){const place=document.createElement('div');wrap.querySelector('.itc-close').before(place);personalPanel=m.mountScheduleNotificationForm(place,{load:async function(){const s=await subscription(false);return enabled()&&s?api('/api/push/schedule-settings/read',{endpoint:s.endpoint}):null;},save:async function(v){const s=await subscription(false);if(!enabled()||!s)throw Error('Нет подписки');return api('/api/push/schedule-settings',Object.assign({endpoint:s.endpoint},v));}});}).catch(function(){});
    var box = wrap.querySelector('#itc-push'), fields = Array.from(wrap.querySelectorAll('[data-push-field]'));
    function busy(value) {
      var current = availability();
      box.disabled = value || (!current.ok && !enabled());
      fields.forEach(function (field) { field.disabled = value || !current.ok; });
      wrap.querySelector('#itc-push-msg').hidden = current.ok;
      wrap.querySelector('#itc-push-msg').textContent = current.msg;
    }
    box.addEventListener('change', function () {
      busy(true);
      (box.checked ? enableFromGesture() : disable()).finally(function () { box.checked = enabled(); busy(false);personalPanel?.refresh(); });
    });
    fields.forEach(function (input) {
      input.addEventListener('change', function () {
        var field = input.dataset.pushField, previous = preference(field);
        setPreference(field, input.checked);
        if (!enabled()) return;
        busy(true);
        syncSubs().catch(function () {
          setPreference(field, previous); input.checked = previous;
          toast('Не удалось сохранить настройку. Проверьте соединение.');
        }).finally(function () { busy(false); });
      });
    });
    wrap.querySelector('#itc-badge').addEventListener('change', function (e) { LS.setItem('itc.pwa.badge', e.target.checked ? '1' : '0'); refreshBadge(); });
    function close() { wrap.remove(); if (opener && opener.isConnected) opener.focus({ preventScroll: true }); }
    wrap.itcClose = close;
    wrap.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    wrap.querySelector('.itc-close').focus({ preventScroll: true });
    wrap.querySelector('.itc-close').addEventListener('click', close);
    wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
  }

  // ---------- значок на иконке: непросмотренные отмены/переносы «Моих кружков» на 2 недели ----------
  function mskDate(offsetDays) { return new Date(Date.now() + 3 * 3600e3 + (offsetDays || 0) * 864e5).toISOString().slice(0, 10); }
  function mskMonday(w) { var d = new Date(Date.now() + 3 * 3600e3); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7 + 7 * w); return d.toISOString().slice(0, 10); }
  function changes() {
    var f = F.Follows.all();
    if (!f.length) return Promise.resolve([]);
    return Promise.all([0, 1].map(function (w) { return window.fetch('/api/schedule?week=' + mskMonday(w)).then(function (r) { return r.ok ? r.json() : []; }, function () { return []; }); }))
      .then(function (weeks) {
        var today = mskDate(0);
        return [].concat(weeks[0], weeks[1]).filter(function (e) { return e && f.indexOf(e.club_id) >= 0 && (e.status === 'cancelled' || e.status === 'moved') && e.date >= today; })
          .map(function (e) { return e.event_id + '|' + e.status + '|' + e.date + '|' + e.start_time; });
      });
  }
  function setBadge(n) {
    var on = LS.getItem('itc.pwa.badge') !== '0';
    root.setAttribute('data-itc-badge', String(on ? n : 0));
    try {
      if (on && n > 0 && navigator.setAppBadge) navigator.setAppBadge(n).catch(function () {});
      else if (navigator.clearAppBadge) navigator.clearAppBadge().catch(function () {});
    } catch (e) { /* нет Badging API */ }
    navigator.serviceWorker?.getRegistration('/').then(function (r) {
      r?.active?.postMessage({ type: 'itc-badge', count: on ? n : 0, enabled: on });
    }).catch(function () {});
  }
  var lastKeys = [];
  function refreshBadge() {
    return changes().then(function (keys) {
      lastKeys = keys;
      var seen = jget(SEEN_KEY, []);
      var unseen = keys.filter(function (k) { return seen.indexOf(k) < 0; }).length;
      setBadge(unseen);
      return unseen;
    });
  }
  // просмотрено = расписание в режиме «Мои» на экране
  function markSeen() {
    if (!F.isMyMode() || doc.hidden || !doc.getElementById('itc-my-toggle')) return;
    jset(SEEN_KEY, lastKeys.slice(-200)); setBadge(0);
  }
  doc.addEventListener('visibilitychange', function () { if (!doc.hidden) { refreshBadge().then(function () { setTimeout(markSeen, 1500); }); syncSubs().catch(function () {}); } });
  doc.addEventListener('itc:follows', function () { setTimeout(refreshBadge, 300); });
  doc.addEventListener('itc:mymode', function () { markSeen(); refreshBadge().then(markSeen); });
  doc.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('#itc-my-toggle')) setTimeout(function () { refreshBadge().then(markSeen); }, 400); });

  window.ItcPwaFeatures = { openSheet: openSheet, enableFromGesture: enableFromGesture, disable: disable, syncSubs: syncSubs,
    refreshBadge: refreshBadge, availability: availability, isEnabled: enabled };

  function boot() {
    dynamicType();
    refreshBadge().then(function () { setTimeout(markSeen, 1500); });
    syncSubs().catch(function () {});
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})();
