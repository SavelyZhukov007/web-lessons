"""Общий стенд для тестов PWA: сборка `server.py build pwa`, сервер на временной БД с демо-данными, Chromium с эмуляцией
установленного PWA (standalone) на iPhone/Android. Эмулятор не нужен."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
ADMIN, PASSWORD = "admin", "Demo-Pass-2026!"

IOS_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"

# Эмуляция standalone: iOS — navigator.standalone (как в Safari «На экран Домой»), Android — display-mode: standalone.
# Плюс моки Notification / PushManager / Badging API, которые записывают вызовы (и была ли активация пользователем).
def init_script(kind: str, standalone: bool = True, share_files: bool = False) -> str:
    return """
(() => {
  const STANDALONE = %s, KIND = '%s', SHARE = %s;
  window.__calls = [];
  const rec = (n, a) => window.__calls.push([n, a === undefined ? null : a]);
  if (STANDALONE) {
    if (KIND === 'ios') Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true, configurable: true });
    const mm = window.matchMedia.bind(window);
    window.matchMedia = q => /display-mode:\\s*standalone/.test(q)
      ? { matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null }
      : mm(q);
  }
  let perm = localStorage.getItem('__qa.perm') || 'default';
  class FakeNotification { constructor(t, o) { rec('notify', t); } static get permission() { return perm; }
    static requestPermission() { rec('requestPermission', { active: !!(navigator.userActivation && navigator.userActivation.isActive) }); perm = 'granted'; localStorage.setItem('__qa.perm', perm); return Promise.resolve(perm); } }
  window.Notification = FakeNotification;
  let sub = localStorage.getItem('__qa.sub') ? JSON.parse(localStorage.getItem('__qa.sub')) : null;
  const wrap = s => s && Object.assign({}, s, { toJSON() { return { endpoint: s.endpoint, keys: s.keys }; }, unsubscribe() { sub = null; localStorage.removeItem('__qa.sub'); return Promise.resolve(true); } });
  if (sub) sub = wrap(sub);
  const mkSub = () => { const raw = { endpoint: 'https://web.push.apple.com/QA-test-' + Math.random().toString(36).slice(2),
    keys: { p256dh: 'BKxQ' + 'A'.repeat(83), auth: 'AAAAAAAAAAAAAAAAAAAAAA' } }; localStorage.setItem('__qa.sub', JSON.stringify(raw)); return wrap(raw); };
  if (!window.PushManager) window.PushManager = function PushManager() {};
  window.PushManager.prototype.getSubscription = function () { return Promise.resolve(sub); };
  window.PushManager.prototype.subscribe = function (o) { rec('pushSubscribe', !!(o && o.applicationServerKey)); sub = sub || mkSub(); return Promise.resolve(sub); };
  navigator.setAppBadge = n => { rec('setAppBadge', n); return Promise.resolve(); };
  navigator.clearAppBadge = () => { rec('clearAppBadge', 0); return Promise.resolve(); };
  if (SHARE) {
    navigator.canShare = d => !!(d && d.files && d.files.length);
    navigator.share = async d => { const f = d.files[0]; rec('share', { name: f.name, type: f.type, text: await f.text() }); };
  } else { navigator.canShare = () => false; }
  // SW: регистрация как в браузере; pushManager подменяем у готовой регистрации
  if (navigator.serviceWorker) {
    const patch = r => { if (r && r.pushManager) { r.pushManager.getSubscription = PushManager.prototype.getSubscription; r.pushManager.subscribe = PushManager.prototype.subscribe; } return r; };
    const gr = navigator.serviceWorker.getRegistration.bind(navigator.serviceWorker);
    navigator.serviceWorker.getRegistration = (...a) => gr(...a).then(patch);
  }
})();
""" % ("true" if standalone else "false", kind, "true" if share_files else "false")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Stand:
    def __init__(self, build: bool = True):
        self.tmp = Path(tempfile.mkdtemp(prefix="pwa-e2e-"))
        self.www = Path(os.environ.get("PWA_DIR") or self.tmp / "pwa")
        py = sys.executable
        self.env = {**os.environ, "CLUBS_SCHEDULE_DB_PATH": str(self.tmp / "e2e.sqlite3"), "ENV": "development",
                    "JWT_SECRET": "pwa-e2e-" + "s" * 40, "VAPID_KEYS_FILE": str(self.tmp / "vapid.json"), "APP_LOGS_DIR": str(self.tmp / "client-logs"), "SCRYPT_LOG_N": "12"}
        self.env.pop("CLUBS_USE_CREATE_ALL", None)
        def run(*a, stdin=None):
            return subprocess.run([py, str(ROOT / "server.py"), *a], cwd=ROOT, env=self.env, input=stdin,
                                  text=True, capture_output=True, check=True, timeout=300)
        if build and not os.environ.get("PWA_DIR"):
            run("build", "pwa", "--out", str(self.www))
        run("seed", "--file", "data/demo-data.json")
        run("admin", "create", ADMIN, "--password-stdin", stdin=PASSWORD + "\n")
        self.port = free_port()
        self.proc = subprocess.Popen([py, str(ROOT / "server.py"), "serve", "--port", str(self.port), "--no-reload", "--frontend", str(self.www)],
                                     cwd=ROOT, env=self.env, stdout=(self.tmp / "server.log").open("w"), stderr=subprocess.STDOUT)
        # localhost — безопасный контекст: service worker и push-API доступны
        self.base = f"http://localhost:{self.port}"
        for _ in range(150):
            try:
                urllib.request.urlopen(self.base + "/readyz", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        else:
            self.stop()
            raise RuntimeError("сервер не поднялся: " + (self.tmp / "server.log").read_text())

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except Exception:  # noqa: BLE001
            self.proc.kill()
