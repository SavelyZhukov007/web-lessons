/* Обновление APK внутри приложения (только Capacitor). GET <url>/api/app/android →
 * {versionCode, versionName, size, sha256, url, changelog[], minSupported}. При запуске и раз в сутки.
 * Новее установленной → шторка «Доступно обновление 1.x» (список изменений, «Обновить» / «Позже»);
 * ниже minSupported — обязательное (без «Позже»). Скачивание в приложении с прогрессом, проверка sha256,
 * системный установщик (REQUEST_INSTALL_PACKAGES + FileProvider). Запасной путь — /android/download в браузере.
 * Адрес: localStorage itc.updateUrl → APP_UPDATE_URL сборки → сервер приложения. Недоступен — молча. */
(function () {
  'use strict';
  var Cap = window.Capacitor;
  if (!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform())) return;
  var U = function () { return Cap.Plugins && Cap.Plugins.ItcUpdate; };
  var BUILD_URL = '%%UPDATE_URL%%';
  var DAY = 864e5, LAST = 'itc.update.last', LATER = 'itc.update.later';
  function endpoint() {
    try { var o = localStorage.getItem('itc.updateUrl'); if (o) return o; } catch (e) {}
    if (BUILD_URL && BUILD_URL.indexOf('%%') < 0) return BUILD_URL;
    var srv = window.AppServer && window.AppServer.get && window.AppServer.get();
    return srv ? srv.replace(/\/+$/, '') + '/api/app/android' : '';
  }
  function toast(t) { if (window.ItcFeatures && window.ItcFeatures.toast) window.ItcFeatures.toast(t); }
  function num(v) { v = parseInt(v, 10); return isFinite(v) ? v : 0; }
  var busy = false;
  function check(opts) {
    opts = opts || {};
    var url = endpoint(), u = U();
    if (!u || busy) return Promise.resolve(null);
    if (!url) { if (opts.manual) toast('Адрес проверки обновлений не задан'); return Promise.resolve(null); }
    busy = true;
    try { localStorage.setItem(LAST, String(Date.now())); } catch (e) {}
    return Promise.all([u.appInfo(), u.check({ url: url })]).then(function (r) {
      var app = r[0] || {}, res = r[1] || {};
      if (res.status !== 200) throw new Error('HTTP ' + res.status);
      var d = JSON.parse(res.body || '{}');
      var latest = num(d.versionCode), mine = num(app.versionCode), min = num(d.minSupported);
      if (!latest || latest <= mine) { if (opts.manual) toast('У вас последняя версия' + (app.versionName ? ' (' + app.versionName + ')' : '')); return null; }
      var forced = min > 0 && mine < min;
      var later = null; try { later = JSON.parse(localStorage.getItem(LATER)); } catch (e) {}
      if (!forced && !opts.manual && later && later.code === latest && Date.now() - later.t < DAY) return null;
      d.download = new URL(d.url || d.download_url || '/android/download', url).href;
      d.page = 'https://github.com/SavelyZhukov007/web-lessons/releases/latest/download/kipclub.apk'; // запасной путь: последний релиз на GitHub
      sheet(d, forced, app);
      return d;
    }).catch(function (e) { if (opts.manual) toast('Не удалось проверить обновления'); return null; })
      .then(function (x) { busy = false; return x; });
  }
  function fmtSize(b) { b = num(b); return b ? (b / 1048576).toFixed(1).replace('.', ',') + ' МБ' : ''; }
  function sheet(d, forced, app) {
    var old = document.getElementById('app-update-sheet'); if (old) old.remove();
    var w = document.createElement('div');
    w.id = 'app-update-sheet'; w.className = 'itc-sheet app-update'; w.setAttribute('role', 'dialog'); w.setAttribute('aria-modal', 'true'); w.setAttribute('aria-labelledby', 'app-update-title');
    if (forced) w.setAttribute('data-forced', '');
    var log = Array.isArray(d.changelog) ? d.changelog : (d.changelog ? String(d.changelog).split(/\n+/) : []);
    var card = document.createElement('div'); card.className = 'itc-sheet-card';
    var h = document.createElement('h2'); h.id = 'app-update-title'; h.textContent = 'Доступно обновление ' + (d.versionName || d.version || '');
    var meta = document.createElement('p'); meta.className = 'itc-muted';
    meta.textContent = (forced ? 'Эта версия больше не поддерживается — обновите приложение, чтобы продолжить. ' : '') +
      (app.versionName ? 'Сейчас: ' + app.versionName + '. ' : '') + (fmtSize(d.size) ? 'Размер: ' + fmtSize(d.size) + '.' : '');
    card.append(h, meta);
    if (log.length) { var ul = document.createElement('ul'); ul.className = 'app-update-log'; log.slice(0, 12).forEach(function (x) { var li = document.createElement('li'); li.textContent = String(x); ul.appendChild(li); }); card.appendChild(ul); }
    var prog = document.createElement('div'); prog.className = 'app-update-progress'; prog.hidden = true;
    prog.innerHTML = '<div class="itc-splash-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-label="Загрузка обновления"><i></i></div><span></span>';
    var msg = document.createElement('p'); msg.className = 'itc-warn'; msg.hidden = true; msg.setAttribute('role', 'status');
    var row = document.createElement('div'); row.className = 'itc-actions';
    var go = document.createElement('button'); go.type = 'button'; go.className = 'btn btn--filled'; go.textContent = 'Обновить';
    var later = document.createElement('button'); later.type = 'button'; later.className = 'btn btn--text'; later.textContent = 'Позже'; later.setAttribute('data-later', '');
    var browser = document.createElement('button'); browser.type = 'button'; browser.className = 'btn btn--text'; browser.textContent = 'Скачать в браузере'; browser.hidden = true;
    if (!forced) row.append(later);
    row.append(browser, go);
    card.append(prog, msg, row); w.appendChild(card); document.body.appendChild(w);
    later.addEventListener('click', function () { try { localStorage.setItem(LATER, JSON.stringify({ code: num(d.versionCode), t: Date.now() })); } catch (e) {} w.remove(); });
    browser.addEventListener('click', function () { U().openExternal({ url: d.page }).catch(function () { location.href = d.page; }); });
    var downloaded = false, listener = null;
    function fail(text) { msg.textContent = text; msg.hidden = false; browser.hidden = false; go.disabled = false; go.textContent = 'Повторить'; prog.hidden = true; }
    function install() {
      return U().install().then(function (r) {
        if (r && r.needsPermission) { msg.textContent = 'Разрешите установку из этого приложения в открывшихся настройках, затем нажмите «Установить».'; msg.hidden = false; go.textContent = 'Установить'; go.disabled = false; }
        else { go.textContent = 'Установка…'; }
      }, function () { fail('Не удалось открыть установщик.'); });
    }
    go.addEventListener('click', function () {
      if (downloaded) { go.disabled = true; install(); return; }
      go.disabled = true; go.textContent = 'Загрузка…'; msg.hidden = true; browser.hidden = true; prog.hidden = false;
      var bar = prog.querySelector('i'), label = prog.querySelector('span'), pb = prog.querySelector('[role=progressbar]');
      Promise.resolve(U().addListener ? U().addListener('progress', function (p) {
        var f = p.total > 0 ? Math.min(1, p.loaded / p.total) : 0;
        bar.style.transform = 'scaleX(' + Math.max(0.03, f) + ')'; pb.setAttribute('aria-valuenow', String(Math.round(f * 100)));
        label.textContent = Math.round(f * 100) + '%' + (p.total > 0 ? ' · ' + fmtSize(p.loaded) + ' из ' + fmtSize(p.total) : '');
      }) : null).then(function (h) { listener = h; });
      if (!/^[0-9a-f]{64}$/i.test(d.sha256 || '')) { fail('Сервер не прислал контрольную сумму — скачайте обновление в браузере.'); return; }
      U().download({ url: d.download, sha256: d.sha256 || '', size: num(d.size) }).then(function () {
        downloaded = true; label.textContent = 'Загружено и проверено'; install();
      }, function (e) {
        var m = String(e && (e.message || e.code) || '');
        fail(/sha256/.test(m) ? 'Файл повреждён (контрольная сумма не совпала). Попробуйте ещё раз или скачайте в браузере.' : 'Не удалось скачать обновление. Проверьте сеть или скачайте в браузере.');
      }).then(function () { if (listener && listener.remove) listener.remove(); });
    });
    w.addEventListener('click', function (e) { if (e.target === w && !forced) later.click(); });
    go.focus();
  }
  function maybe() { var t = 0; try { t = num(localStorage.getItem(LAST)); } catch (e) {} if (Date.now() - t > DAY) check(); }
  window.ItcAppUpdate = { check: check, endpoint: endpoint };
  // при запуске (после экрана загрузки, чтобы не мешать первому контенту) и раз в сутки
  function boot() {
    setTimeout(function () { if (!sessionStorage.getItem('itc.updateChecked')) { sessionStorage.setItem('itc.updateChecked', '1'); check(); } else maybe(); }, 2500);
    setInterval(function () { if (!document.hidden) maybe(); }, 3600e3);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) maybe(); });
  }
  if (/^\/admin\/|^\/settings\.html/.test(location.pathname)) return; // не мешаем вводу в админке и настройках
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
