/* Экран загрузки APK (только Capacitor). Подключается prepare-web.mjs синхронно в <head>, разметка #itc-splash — первым
 * элементом <body>. Холодный старт (первая страница процесса): брендовый экран — иконка на фирменном круге (как у системного
 * SplashScreen Android 12+, поэтому передача без второго сплэша), полоса прогресса по реальным этапам загрузки
 * (DOM → скрипты → кэш/запрос → данные → отрисовка), весёлые фразы, версия и «Продукт ИТС КИПФИН». Не меньше ~600 мс.
 * Повторные переходы внутри приложения — без экрана. API: window.ItcSplash.progress(0..1), .done(). */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  if (!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform())) return;
  var doc = document, root = doc.documentElement;
  var VERSION = '%%VERSION%%';
  var MIN_MS = 600, MAX_MS = 8000;
  var cold = false;
  try { cold = !sessionStorage.getItem('itc.booted'); } catch (e) { cold = false; }
  function plugin() { return Cap.Plugins && Cap.Plugins.ItcUpdate; }
  function handover() { // веб нарисовал первый кадр → системный сплэш убирается
    requestAnimationFrame(function () { setTimeout(function () { try { plugin() && plugin().splashReady().catch(function () {}); } catch (e) {} }, 0); });
  }
  var api = { progress: function () {}, done: function () {}, cold: cold, version: VERSION };
  window.ItcSplash = api;
  if (!cold) { doc.addEventListener('DOMContentLoaded', handover); return; }
  root.classList.add('itc-splash-on');
  var PHRASES = ['Открываем приложение…', 'Сверяем расписание…', 'Будим преподавателей…', 'Ищем свободную аудиторию…',
    'Заряжаем кружки…', 'Точим карандаши…', 'Расставляем стулья…', 'Протираем доску…', 'Проверяем звонки…',
    'Включаем проектор…', 'Считаем кружки по пальцам…', 'Ищем ключ от кабинета…', 'Настраиваем гитары…',
    'Разминаемся перед занятием…', 'Раскладываем шахматы…', 'Варим кофе преподавателям…', 'Наводим порядок в журнале…',
    'Ловим вдохновение…', 'Собираем команду…', 'Синхронизируем часы с Москвой…', 'Сдуваем пыль с конспектов…',
    'Заряжаем маркеры…', 'Поливаем кактус в учительской…', 'Почти готово…'];
  var shown = 0, target = 0.08, finished = false, t0 = performance.now(), el = null, bar = null, phrase = null, timer = 0;
  function paint() { if (bar) bar.style.transform = 'scaleX(' + Math.max(shown, 0.04) + ')'; if (el) el.setAttribute('aria-valuenow', String(Math.round(shown * 100))); }
  function tick() { // плавно догоняем реальный прогресс, не обгоняя его
    if (!el) return;
    shown += (target - shown) * 0.25; if (target - shown < 0.004) shown = target; paint();
    if (shown < 1) requestAnimationFrame(tick);
  }
  api.progress = function (p) { if (finished) return; target = Math.max(target, Math.min(0.97, +p || 0)); requestAnimationFrame(tick); };
  api.done = function () {
    if (finished) return; finished = true;
    var wait = Math.max(0, MIN_MS - (performance.now() - t0));
    setTimeout(function () {
      target = 1; shown = 1; paint();
      try { sessionStorage.setItem('itc.booted', '1'); } catch (e) {}
      setTimeout(function () {
        root.classList.add('itc-splash-out');
        setTimeout(function () { clearInterval(timer); if (el) el.remove(); root.classList.remove('itc-splash-on', 'itc-splash-out'); }, 260);
      }, 120);
    }, wait);
  };
  function mount() {
    el = doc.getElementById('itc-splash'); if (!el) { api.done(); return; }
    bar = el.querySelector('.itc-splash-bar i'); phrase = el.querySelector('.itc-splash-phrase');
    var v = el.querySelector('.itc-splash-version'); if (v) v.textContent = 'Версия ' + VERSION;
    var i = Math.floor(Math.random() * 3); phrase.textContent = PHRASES[0];
    timer = setInterval(function () {
      i = (i % (PHRASES.length - 1)) + 1;
      phrase.classList.add('swap');
      setTimeout(function () { phrase.textContent = PHRASES[i]; phrase.classList.remove('swap'); }, 160);
    }, 1100);
    handover();
    /* 'lifted' убран: позиция логотипа фиксирована, без прыжка */
    api.progress(0.3);
    // страницы без своего сигнала (кружок, каталог, админка) — готовы по load
    if (!doc.getElementById('schedule-main')) window.addEventListener('load', function () { api.progress(0.9); api.done(); });
    setTimeout(api.done, MAX_MS);
  }
  // t100 perf: прогрев, пока виден сплэш — следующие экраны (каталог, админка) открываются уже из кэша WebView,
  // а JIT успевает разобрать их скрипты. Только в простое и только на холодном старте.
  function warm() {
    var idle = window.requestIdleCallback || function (f) { return setTimeout(f, 300); };
    idle(function () {
      ['/clubs.html'].forEach(function (u) {
        var l = doc.createElement('link'); l.rel = 'prefetch'; l.href = u; doc.head.appendChild(l);
      });
      try { if (/"role":"admin"/.test(localStorage.getItem('itc.session') || '')) { var a = doc.createElement('link'); a.rel = 'prefetch'; a.href = '/admin/index.html'; doc.head.appendChild(a); } } catch (e) {}
    }, { timeout: 1500 });
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', function () { mount(); warm(); }); else { mount(); warm(); }
})();
