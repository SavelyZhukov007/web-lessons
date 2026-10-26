// Счётчик пользователей: анонимный id установки (localStorage) → POST /api/app/ping раз в день и при возврате в приложение
// (не чаще раза в час). Сервер хранит только хэш id и вид (сайт / PWA на iPhone / другое PWA) — без IP и User-Agent.
// В APK этот файл не подключается: установки Android считаются по регистрации устройства.
const ID_KEY = 'kc.installId', LAST_KEY = 'kc.pingAt', HOUR = 3600e3;

function installId() {
  try {
    let id = localStorage.getItem(ID_KEY);
    if (!id) {
      const b = new Uint8Array(16); crypto.getRandomValues(b);
      id = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
      localStorage.setItem(ID_KEY, id);
    }
    return id;
  } catch { return null; } // приватный режим без хранилища — не считаем
}

export function kind() {
  const mm = q => { try { return matchMedia(q).matches; } catch { return false; } };
  const standalone = navigator.standalone === true || mm('(display-mode: standalone)') || mm('(display-mode: fullscreen)');
  if (!standalone) return 'web';
  const ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios ? 'ios-pwa' : 'pwa';
}

function ping(force) {
  if (window.Capacitor?.isNativePlatform?.()) return;
  const id = installId(); if (!id) return;
  let last = 0; try { last = +localStorage.getItem(LAST_KEY) || 0; } catch { /* ignore */ }
  const today = new Date().toDateString() !== new Date(last).toDateString();
  if (!today && !(force && Date.now() - last > HOUR)) return;
  try { localStorage.setItem(LAST_KEY, String(Date.now())); } catch { /* ignore */ }
  fetch('/api/app/ping', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ install_id: id, kind: kind() }), keepalive: true })
    .catch(() => { try { localStorage.setItem(LAST_KEY, String(last)); } catch { /* ignore */ } });
}

ping(false);
document.addEventListener('visibilitychange', () => { if (!document.hidden) ping(true); });
