(function () {
  'use strict';
  var S = window.AppServer;
  var $ = function (id) { return document.getElementById(id); };
  var input = $('server-url'), status = $('status');
  var cur = S.get();
  input.value = cur;
  if (cur) { $('back').hidden = false; $('reset').hidden = false; $('direct').hidden = false; $('first-hint').textContent = 'Текущий сервер: ' + cur; }
  function show(kind, text) { status.className = kind; status.textContent = text; }
  function setBusy(b) { $('test').disabled = b; $('save').disabled = b; }
  var lastOk = null;

  function runTest() {
    show('busy', 'Проверяю соединение…'); setBusy(true); $('force').hidden = true;
    return S.test(input.value).then(function (r) {
      lastOk = r; show('ok', 'Сервер отвечает ✔  ' + r.base + '  (кружков: ' + r.clubs + ')'); return r;
    }).catch(function (e) { lastOk = null; show('err', e.message); throw e; })
      .finally(function () { setBusy(false); });
  }
  $('test').addEventListener('click', function () { runTest().catch(function () {}); });
  $('form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    runTest().then(function (r) { S.set(r.base); location.href = '/'; })
      .catch(function () { $('force').hidden = false; });
  });
  $('force').addEventListener('click', function () {
    try { S.set(input.value); location.href = '/'; } catch (e) { show('err', e.message); }
  });
  $('reset').addEventListener('click', function () { S.clear(); location.replace('/settings.html?first=1'); });
  // Запасной режим: открыть сам сайт в WebView (тот же origin => cookie и CORS без забот)
  $('direct').addEventListener('click', function () { var b = S.get(); if (b) location.href = b + '/'; });
})();
