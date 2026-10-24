/* Анимации APK (phase 2 C): переходы экранов, шторки, диалоги, фильтры, вкладки, дни, списки, тосты, аккордеоны, тема, удаление.
 * Только transform/opacity (WAAPI/CSS), токены — css/native-motion.css. View Transitions там, где WebView умеет, иначе — запасной вариант.
 * Вне Capacitor.isNativePlatform() ничего не делает. */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  var NATIVE = !!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform());
  var PWA = !NATIVE && window.ItcPwa === true; // установленное PWA (standalone) — флаг ставит pwa-standalone.js только в сборке pwa
  if (!NATIVE && !PWA) return;
  var doc = document, root = doc.documentElement;
  (function () { if (doc.querySelector('link[href="/css/native-motion.css"]')) return; var l = doc.createElement('link'); l.rel = 'stylesheet'; l.href = '/css/native-motion.css'; doc.head.appendChild(l); })();

  var reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var DUR = { s: 180, m: 240, l: 280 };
  var EASE = { std: 'cubic-bezier(.2,0,0,1)', dec: 'cubic-bezier(.05,.7,.1,1)', acc: 'cubic-bezier(.3,0,.8,.15)' };
  var crossDocVT = !!(window.CSS && CSS.supports && CSS.supports('selector(:active-view-transition-type(a))'));
  var busyN = 0;
  function busy(ms) { busyN++; root.classList.add('m-busy'); setTimeout(function () { if (--busyN <= 0) { busyN = 0; root.classList.remove('m-busy'); } }, ms); }
  function anim(el, frames, ms, easing) {
    if (!el || !el.animate) return Promise.resolve();
    if (reduced) frames = frames.map(function (f) { return { opacity: f.opacity == null ? 1 : f.opacity }; });
    return el.animate(frames, { duration: ms, easing: easing || EASE.std, fill: 'none' }).finished.catch(function () {});
  }
  window.ItcMotion = { anim: anim, busy: busy, DUR: DUR, EASE: EASE };

  // ---------- 1. переходы между экранами ----------
  var DIR = 'm.dir';
  function markBack() { try { sessionStorage.setItem(DIR, 'back'); } catch (e) {} }
  var P = (NATIVE && Cap.Plugins) || {};
  if (P.App && P.App.addListener) P.App.addListener('backButton', markBack); // системная «Назад» и жест
  window.addEventListener('popstate', markBack);
  function takeDir(nav) {
    var d = 'fwd';
    try { if (sessionStorage.getItem(DIR) === 'back') d = 'back'; sessionStorage.removeItem(DIR); } catch (e) {}
    if (nav && nav.navigationType === 'traverse') d = 'back';
    return d;
  }
  if (crossDocVT) {
    window.addEventListener('pagereveal', function (e) {
      if (!e.viewTransition) return;
      ['ready', 'finished', 'updateCallbackDone'].forEach(function (k) { var pr = e.viewTransition[k]; if (pr && pr.catch) pr.catch(function () {}); });
      var d = takeDir(window.navigation && navigation.activation);
      if (d === 'back') e.viewTransition.types.add('back');
      busy(DUR.l);
    });
  } else {
    var d0 = takeDir(window.navigation && navigation.activation);
    root.classList.add(d0 === 'back' ? 'm-enter-back' : 'm-enter-fwd');
    busy(DUR.l);
    setTimeout(function () { root.classList.remove('m-enter-back', 'm-enter-fwd'); }, DUR.l + 40);
    doc.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey) return;
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || a.target || a.hasAttribute('download')) return;
      var u = new URL(a.href, location.href);
      if (u.origin !== location.origin || /^\/api\//.test(u.pathname) || (u.pathname === location.pathname && u.search === location.search)) return;
      e.preventDefault();
      var back = a.classList.contains('public-back') || /назад|к списку|к расписанию/i.test(a.textContent);
      if (back) markBack();
      root.classList.add(back ? 'm-leave-back' : 'm-leave-fwd');
      busy(DUR.s + 400);
      setTimeout(function () { location.href = a.href; }, DUR.s - 20);
    });
    window.addEventListener('pageshow', function (e) { if (e.persisted) root.classList.remove('m-leave-back', 'm-leave-fwd'); });
  }
  // «Назад» по ссылкам «К списку…» в режиме View Transitions — тоже обратное направление
  doc.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a.public-back, a.back-link');
    if (a) markBack();
  }, true);

  // ---------- 2. вкладки админки: кросс-фейд + движение индикатора ----------
  var adminMain = function () { return doc.getElementById('admin-main'); };
  window.addEventListener('hashchange', function () {
    var m = adminMain(); if (!m) return;
    m.classList.remove('m-swap'); void m.offsetWidth; m.classList.add('m-swap');
    busy(DUR.m);
  });
  function indicator(container, sel, cls, fit) {
    if (!container) return;
    var cur = container.querySelector(sel);
    var ind = container.querySelector(':scope > .m-ind');
    if (!cur) { if (ind) ind.style.opacity = '0'; return; }
    if (!ind) { ind = doc.createElement('span'); ind.className = 'm-ind'; ind.setAttribute('aria-hidden', 'true'); container.appendChild(ind); container.classList.add(cls || 'm-has-ind'); }
    var cr = container.getBoundingClientRect(), r = (fit ? fit(cur) : cur).getBoundingClientRect();
    ind.style.opacity = '1';
    ind.style.width = r.width + 'px'; ind.style.height = r.height + 'px'; ind.style.top = (r.top - cr.top) + 'px';
    ind.style.transform = 'translateX(' + (r.left - cr.left + container.scrollLeft) + 'px)';
  }
  function navIndicators() {
    doc.querySelectorAll('.bottom-nav').forEach(function (n) {
      if (getComputedStyle(n).position !== 'static') indicator(n, 'a[aria-current="page"]', 'm-has-ind', function (a) { return a.querySelector('.bn-pill') || a; });
    });
  }

  // ---------- 3. смена дня: кросс-фейд списка ----------
  doc.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('#day-buttons > button, #prev-day, #next-day, #view-grid, #view-list');
    if (!b) return;
    var c = doc.getElementById('content');
    if (c) { c.classList.remove('m-xfade'); void c.offsetWidth; c.classList.add('m-xfade'); }
    requestAnimationFrame(function () {
      navIndicators();
      var sel = doc.querySelector('#day-buttons > button[aria-pressed="true"]');
      if (sel) anim(sel, [{ opacity: .55 }, { opacity: 1 }], DUR.m, EASE.dec); // без scale: ячейка не может «залипнуть» увеличенной
    });
  });

  // ---------- 4. панель фильтров: плавное раскрытие/сворачивание ----------
  var replaying = false;
  doc.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('#toggle-filters');
    if (!t || replaying) return;
    var panel = doc.getElementById('filter-options');
    if (!panel) return;
    if (t.getAttribute('aria-expanded') === 'true') {
      e.preventDefault(); e.stopImmediatePropagation(); busy(DUR.s);
      anim(panel, [{ opacity: 1, transform: 'scaleY(1)' }, { opacity: 0, transform: 'scaleY(.85) translateY(-8px)' }], DUR.s, EASE.acc).then(function () {
        replaying = true; t.click(); replaying = false;
      });
    } else {
      setTimeout(function () { if (!panel.hidden) { busy(DUR.m); anim(panel, [{ opacity: 0, transform: 'scaleY(.85) translateY(-8px)' }, { opacity: 1, transform: 'none' }], DUR.m, EASE.dec); } }, 0);
    }
  }, true);

  // ---------- 5. аккордеоны <details> ----------
  doc.addEventListener('click', function (e) {
    var s = e.target.closest && e.target.closest('details > summary');
    if (!s || replaying) return;
    var d = s.parentElement, body = Array.prototype.filter.call(d.children, function (x) { return x !== s; });
    if (!d.open) {
      setTimeout(function () { body.forEach(function (b) { anim(b, [{ opacity: 0, transform: 'translateY(-6px)' }, { opacity: 1, transform: 'none' }], DUR.m, EASE.dec); }); }, 0);
    } else {
      e.preventDefault(); busy(DUR.s);
      Promise.all(body.map(function (b) { return anim(b, [{ opacity: 1 }, { opacity: 0, transform: 'translateY(-6px)' }], DUR.s, EASE.acc); }))
        .then(function () { d.open = false; });
    }
  }, true);

  // ---------- 6. диалоги и шторки: анимированное закрытие + свайп вниз ----------
  var D = window.HTMLDialogElement && HTMLDialogElement.prototype;
  if (D && D.close) {
    var nativeClose = D.close;
    D.close = function (v) {
      var dlg = this;
      if (!dlg.open || dlg.classList.contains('m-closing')) return nativeClose.call(dlg, v);
      dlg.classList.add('m-closing'); busy(DUR.s);
      var sheet = dlg.classList.contains('sheet--bottom');
      anim(dlg, sheet ? [{ transform: getComputedStyle(dlg).transform === 'none' ? 'none' : getComputedStyle(dlg).transform }, { transform: 'translateY(100%)' }]
        : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.95)' }], DUR.s, EASE.acc)
        .then(function () { dlg.classList.remove('m-closing'); dlg.style.transform = ''; nativeClose.call(dlg, v); });
    };
    doc.addEventListener('cancel', function (e) { if (e.target.tagName === 'DIALOG') { e.preventDefault(); e.target.close(); } }, true);
  }
  function swipeToDismiss(sheet, close) {
    if (sheet.dataset.mSwipe) return; sheet.dataset.mSwipe = '1';
    var y0 = null, dy = 0, t0 = 0;
    sheet.addEventListener('touchstart', function (e) {
      if (sheet.scrollTop > 0 || e.touches.length !== 1) { y0 = null; return; }
      y0 = e.touches[0].clientY; dy = 0; t0 = Date.now();
    }, { passive: true });
    sheet.addEventListener('touchmove', function (e) {
      if (y0 == null) return;
      dy = Math.max(0, e.touches[0].clientY - y0);
      sheet.style.transform = dy ? 'translateY(' + dy + 'px)' : '';
    }, { passive: true });
    sheet.addEventListener('touchend', function () {
      if (y0 == null) return; y0 = null;
      var fast = dy > 40 && dy / Math.max(1, Date.now() - t0) > 0.5;
      if (dy > sheet.offsetHeight * 0.3 || fast) close();
      else if (dy) anim(sheet, [{ transform: 'translateY(' + dy + 'px)' }, { transform: 'none' }], DUR.s, EASE.dec).then(function () { sheet.style.transform = ''; });
      else sheet.style.transform = '';
    });
  }
  function wireSheets() {
    doc.querySelectorAll('dialog.sheet--bottom[open]').forEach(function (d) { swipeToDismiss(d, function () { d.close(); }); });
    doc.querySelectorAll('.itc-sheet .itc-sheet-card').forEach(function (card) {
      var wrap = card.parentElement;
      if (wrap.dataset.mPatched) return; wrap.dataset.mPatched = '1';
      var close = function () {
        busy(DUR.s);
        Promise.all([anim(card, [{ transform: card.style.transform || 'none' }, { transform: 'translateY(100%)' }], DUR.s, EASE.acc),
          anim(wrap, [{ opacity: 1 }, { opacity: 0 }], DUR.s)]).then(function () { wrap.remove(); });
      };
      // перехватываем «Готово» и тап по фону
      wrap.addEventListener('click', function (e) {
        if (e.target === wrap || (e.target.closest && e.target.closest('.itc-close'))) { e.stopImmediatePropagation(); close(); }
      }, true);
      swipeToDismiss(card, close);
    });
  }

  // ---------- 7. удаление: строка схлопывается перед удалением ----------
  var doomed = null;
  doc.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('button');
    if (!b || replaying) return;
    var label = (b.getAttribute('aria-label') || b.textContent || '').trim();
    var row = b.closest('tr, li, .card, .club-card');
    if (/^(Удалить|Скрыть)/.test(label) && row && !b.closest('dialog')) { doomed = row; return; }
    var dlg = b.closest('dialog');
    if (dlg && doomed && /btn--danger|danger/.test(b.className) && /Удалить|Скрыть/.test(label)) {
      e.preventDefault(); e.stopImmediatePropagation();
      var r = doomed; doomed = null; busy(DUR.m);
      replaying = true; b.click(); replaying = false; // подтверждение уходит сразу; строка схлопывается, пока идёт запрос
      collapse(r);
    }
  }, true);
  function collapse(el) {
    if (!el || !el.isConnected) return Promise.resolve();
    var ghost = el.cloneNode(true), r = el.getBoundingClientRect();
    ghost.style.cssText += ';position:fixed;left:' + r.left + 'px;top:' + r.top + 'px;width:' + r.width + 'px;height:' + r.height + 'px;margin:0;z-index:40;pointer-events:none;transform-origin:top center;display:block;background:var(--surface-1, var(--bg));';
    ghost.classList.add('m-fixed');
    el.style.opacity = '0';
    doc.body.appendChild(ghost);
    return anim(ghost, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scaleY(.4) translateX(24px)' }], DUR.m, EASE.acc).then(function () { ghost.remove(); });
  }
  var nativeRemove = Element.prototype.remove;
  Element.prototype.remove = function () {
    var el = this;
    if (el.isConnected && el.matches && el.matches('.snackbar, .itc-toast') && !el.dataset.mGone) {
      el.dataset.mGone = '1';
      anim(el, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(12px)' }], DUR.s, EASE.acc).then(function () { nativeRemove.call(el); });
      return;
    }
    return nativeRemove.call(el);
  };
  window.ItcMotion.collapse = collapse;

  // ---------- 8. тема: плавная смена вместо вспышки ----------
  var setAttr = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (this === root && name === 'data-theme' && root.getAttribute('data-theme') && root.getAttribute('data-theme') !== value && doc.readyState !== 'loading') {
      var el = this;
      if (doc.hidden || doc.readyState !== 'complete') return setAttr.call(el, name, value); // при загрузке — без анимации
      var quiet = function (vt) { if (vt) ['ready', 'finished', 'updateCallbackDone'].forEach(function (k) { if (vt[k] && vt[k].catch) vt[k].catch(function () {}); }); };
      if (doc.startViewTransition) {
        try { quiet(doc.startViewTransition({ update: function () { setAttr.call(el, name, value); }, types: ['theme'] })); busy(DUR.l); return; }
        catch (e) { try { quiet(doc.startViewTransition(function () { setAttr.call(el, name, value); })); return; } catch (e2) { /* ниже */ } }
      }
      var veil = doc.createElement('div');
      veil.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;background:' + getComputedStyle(doc.body).backgroundColor;
      doc.body.appendChild(veil);
      setAttr.call(el, name, value);
      anim(veil, [{ opacity: 1 }, { opacity: 0 }], DUR.l).then(function () { veil.remove(); });
      return;
    }
    return setAttr.call(this, name, value);
  };

  // ---------- 9. элементы списков: появление по очереди ----------
  var LIST_ITEMS = '#content > *, #content .calendar-event, #content .day-column, .clubs-grid > *, a.club-card, .admin-main table.data tbody > tr, .admin-main .stat-card, .admin-main .card';
  var seen = new WeakSet(), batch = [], queued = false;
  function stagger() {
    queued = false;
    var items = batch.filter(function (el) { return el.isConnected; }); batch = [];
    items.slice(0, 12).forEach(function (el, i) {
      el.style.setProperty('--m-i', String(i));
      el.classList.remove('m-item-in'); void el.offsetWidth; el.classList.add('m-item-in');
      setTimeout(function () { el.classList.remove('m-item-in'); el.style.removeProperty('--m-i'); }, DUR.m + i * 30 + 60);
    });
  }
  function collect() {
    doc.querySelectorAll(LIST_ITEMS).forEach(function (el) {
      if (seen.has(el) || el.closest('.m-fixed') || el.classList.contains('skeleton-block')) return;
      seen.add(el); batch.push(el);
    });
    if (batch.length && !queued) { queued = true; requestAnimationFrame(stagger); }
  }

  var pend = false;
  function onMut() {
    if (pend) return; pend = true;
    requestAnimationFrame(function () { pend = false; collect(); wireSheets(); navIndicators(); });
  }
  function boot() {
    new MutationObserver(onMut).observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-current', 'aria-pressed', 'open'] });
    window.addEventListener('resize', navIndicators);
    onMut();
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})();
