/* Установленное PWA (phase 2 D). Подключается сборкой `server.py build pwa` в <head> сразу после theme-init.js.
 * В обычной вкладке браузера НИЧЕГО не делает: сайт остаётся прежним. В режиме standalone (иконка на экране «Домой»
 * на iPhone/iPad или установленное PWA на Android) включает ту же оболочку, что и APK: правки вида, анимации,
 * «Мои кружки», офлайн-кэш, QR — плюс web push для «Моих кружков», значок на иконке и .ics (pwa-features.js). */
(function () {
  'use strict';
  var w = window, doc = document, root = doc.documentElement;
  function mm(q) { try { return !!(w.matchMedia && w.matchMedia(q).matches); } catch (e) { return false; } }
  var standalone = w.navigator.standalone === true || mm('(display-mode: standalone)') || mm('(display-mode: fullscreen)');
  if (!standalone || (w.Capacitor && w.Capacitor.isNativePlatform && w.Capacitor.isNativePlatform())) return;
  w.ItcPwa = true;
  var ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  root.classList.add('is-pwa', ios ? 'is-pwa-ios' : 'is-pwa-other');
  // Порядок как в APK: оболочка → функции → анимации → PWA-часть. document.write — синхронно, до модулей страницы,
  // чтобы обёртка fetch (офлайн-кэш, «Мои») стояла раньше первого запроса.
  // стили — парсером (блокируют первую отрисовку): без «мигания» и с opt-in @view-transition до pagereveal
  doc.write('<link rel="stylesheet" href="/css/native-shell.css" data-native-shell><link rel="stylesheet" href="/css/native-features.css">' +
            '<link rel="stylesheet" href="/css/native-motion.css"><link rel="stylesheet" href="/css/app-student.css"><link rel="stylesheet" href="/pwa/pwa.css" data-pwa-css>');
  doc.write('<script src="/js/native-shell.js"></script><script src="/js/native-features.js"></script>' +
            '<script src="/js/native-motion.js"></script><script src="/js/app-admin.js" defer></script><script src="/pwa/pwa-features.js"></script>');
  // Opening the public timetable must not require choosing a role. The private
  // student profile is needed only on the check-in screen.
  if (/\/qr\.html$/.test(location.pathname)) doc.write('<script src="/js/app-student.js"></script>');
})();
