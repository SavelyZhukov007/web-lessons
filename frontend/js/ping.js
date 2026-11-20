// Уровень Б перенесён в usage.js (ping раз в день со случайным id установки, только при включённой «Анонимной статистике»).
// Файл оставлен, чтобы старые страницы и pwa-register.js продолжали работать.
import './usage.js';

export function kind() {
  const mm = q => { try { return matchMedia(q).matches; } catch { return false; } };
  const standalone = navigator.standalone === true || mm('(display-mode: standalone)') || mm('(display-mode: fullscreen)');
  if (!standalone) return 'web';
  const ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios ? 'ios-pwa' : 'pwa';
}
