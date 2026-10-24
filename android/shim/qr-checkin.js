/* Отметка посещения: студент сканирует ротируемый QR преподавателя (в APK — нативный сканер ItcScanner: CameraX + ML Kit;
 * в браузере — jsQR + getUserMedia в полноэкранном видоискателе)
 * и отправляет {student_id, session_id, qr_token, nonce, device_token}. Имя не отправляется. Без сети отметка встаёт
 * в очередь (ItcQueue) с реальным временем сканирования scanned_at — сервер проверит её на тот момент. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var video = $('qr-video'), canvas = $('qr-canvas'), status = $('qr-status'), who = $('qr-who');
  var stream = null, busy = false, me = null;
  var H = window.ItcHaptics || { success: function () {}, error: function () {}, tap: function () {} };
  function say(text, kind) { status.textContent = text; status.className = 'itc-qr-status ' + (kind || ''); }
  function stop() { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; $('qr-cam').hidden = true; document.documentElement.classList.remove('itc-cam-open'); }
  function nonce() { var a = new Uint8Array(16); crypto.getRandomValues(a); return btoa(String.fromCharCode.apply(null, a)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
  function sessionOf(token) { try { return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).s; } catch (e) { return null; } }
  function checkin(token) {
    token = String(token || '').trim();
    if (!me) { say('Сначала заполните профиль студента', 'err'); return; }
    if (token.indexOf('itc-att2.') !== 0 || !sessionOf(token)) { H.error(); say('Это не QR-код посещаемости ИТК', 'err'); return; }
    busy = true; say('Отправляем…');
    var body = { student_id: me.id, session_id: sessionOf(token), qr_token: token, nonce: nonce(), device_token: me.device, scanned_at: Date.now() / 1000 };
    var Q = window.ItcQueue;
    var queueIt = function () { if (!Q) return false; Q.add({ body: body, at: Date.now() }); H.success(); say('Нет сети — отметка сохранена и отправится сама, как только появится интернет', 'pending'); paintQueue(); return true; };
    if (!navigator.onLine && queueIt()) { busy = false; return; }
    fetch('/api/attendance/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 201) { H.success(); say('✓ Вы отмечены: ' + j.club_name + ', ' + j.start_time + '–' + j.end_time, 'ok'); }
          else { H.error(); say(window.ItcHuman ? window.ItcHuman.error(r.status, j && j.detail) : 'Не получилось отметиться. Попробуйте ещё раз', /Уже отмечен/.test(j && j.detail) ? 'ok' : 'err'); }
        });
      }, function () { if (!queueIt()) { H.error(); say('Нет сети. Подключитесь к интернету и отсканируйте код ещё раз', 'err'); } })
      .then(function () { busy = false; });
  }
  function paintQueue() {
    var a = window.ItcQueue ? window.ItcQueue.list() : [], box = $('qr-queue');
    if (!box) { box = document.createElement('div'); box.id = 'qr-queue'; box.className = 'itc-queue'; status.after(box); }
    box.hidden = !a.length;
    box.innerHTML = a.length ? '<b>Ожидают отправки: ' + a.length + '</b>' + a.map(function (x) {
      return '<span class="itc-queue-row"><i class="itc-queue-dot" aria-hidden="true"></i>Отсканировано в ' + new Date(x.at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) + ' · ждёт сети</span>'; }).join('') : '';
  }
  document.addEventListener('itc:queue', paintQueue);
  function tick() {
    if (!stream) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA && !busy) {
      var w = video.videoWidth, h = video.videoHeight, s = Math.min(1, 640 / Math.max(w, h));
      canvas.width = w * s; canvas.height = h * s;
      var ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      var code = window.jsQR && jsQR(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height, { inversionAttempts: 'dontInvert' });
      if (code && code.data) { stop(); H.tap(); checkin(code.data); return; }
    }
    requestAnimationFrame(tick);
  }
  var Scanner = window.Capacitor && Capacitor.isNativePlatform && Capacitor.isNativePlatform() && Capacitor.Plugins && Capacitor.Plugins.ItcScanner;
  function start() {
    if (!me) { if (window.ItcStudent) window.ItcStudent.profileScreen({ onboarding: true }); return; }
    say('');
    if (Scanner) { // нативный полноэкранный сканер (CameraX + ML Kit)
      Scanner.scan({ hint: 'Наведите камеру на QR-код преподавателя' }).then(function (r) {
        if (r && r.text) { H.tap(); checkin(r.text); }
      }, function (e) {
        say(e && e.code === 'camera-denied' ? 'Нет доступа к камере. Разрешите его в настройках телефона или введите код вручную'
          : 'Камера недоступна — введите код вручную', 'err');
      });
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { say('Камера недоступна — введите код вручную', 'err'); return; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false }).then(function (s) {
      stream = s; video.srcObject = s; video.play(); $('qr-cam').hidden = false; document.documentElement.classList.add('itc-cam-open');
      var tr = s.getVideoTracks()[0], caps = tr && tr.getCapabilities ? tr.getCapabilities() : {};
      $('qr-torch').hidden = !caps.torch; torchOn = false;
      requestAnimationFrame(tick);
    }, function () { say('Нет доступа к камере. Разрешите его в настройках приложения или введите код вручную', 'err'); });
  }
  var torchOn = false;
  $('qr-torch').addEventListener('click', function () {
    var tr = stream && stream.getVideoTracks()[0]; if (!tr) return;
    torchOn = !torchOn; tr.applyConstraints({ advanced: [{ torch: torchOn }] }).catch(function () {});
    this.classList.toggle('on', torchOn);
  });
  $('qr-close').addEventListener('click', stop);
  function copyId() {
    var t = me && me.id; if (!t) return;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { say('ID скопирован', 'ok'); }, function () { say('Не удалось скопировать — выделите ID вручную', 'err'); });
  }
  function paintWho() {
    if (me) {
      who.innerHTML = '<div class="itc-idrow"><span>Ваш ID</span><code></code><button type="button" class="itc-copy" aria-label="Скопировать ID"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/></svg></button></div>';
      who.querySelector('code').textContent = me.id; who.querySelector('.itc-copy').addEventListener('click', copyId); return;
    }
    who.innerHTML = '<p class="itc-muted">Для отметки нужен профиль студента (ФИО и группа хранятся только на телефоне).</p>';
    var b = document.createElement('button'); b.type = 'button'; b.className = 'itc-primary'; b.textContent = 'Заполнить профиль';
    b.addEventListener('click', function () { window.ItcStudent.profileScreen({ onboarding: true }); }); who.appendChild(b);
  }
  $('qr-start').addEventListener('click', start);
  $('qr-manual').addEventListener('submit', function (e) { e.preventDefault(); checkin($('qr-code').value); });
  window.addEventListener('pagehide', stop);
  var load = window.ItcStudent ? window.ItcStudent.load() : Promise.resolve(null);
  load.then(function (st) {
    me = st; paintWho(); paintQueue();
    var t = new URLSearchParams(location.search).get('token');
    if (t) checkin(t); else if (me && new URLSearchParams(location.search).get('scan') === '1') start(); // ярлык/уведомление «Отметиться»
  });
  // профиль заполнили прямо отсюда → обновить
  document.addEventListener('visibilitychange', function () { if (!document.hidden && !me && window.ItcStudent) window.ItcStudent.load().then(function (st) { me = st; paintWho(); }); });
  setInterval(function () { if (!me && window.ItcStudent && localStorage.getItem('itc.vault.v1')) window.ItcStudent.load().then(function (st) { if (st) { me = st; paintWho(); } }); }, 1500);
})();
