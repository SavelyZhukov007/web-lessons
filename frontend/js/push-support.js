// Чистая логика «можно ли подписаться на push» — без обращения к DOM, чтобы проверять в node:test.
/** @param {{native?:boolean, secure:boolean, hasSW:boolean, hasPush:boolean, hasNotification:boolean, platform:string, standalone:boolean, permission:string}} env */
export function pushAvailability(env) {
  if (env.native) return { state: 'native', message: 'В приложении уведомления приходят через Firebase, а если он недоступен — фоновой проверкой расписания (раз в ~30 минут). Включить или выключить их можно в настройках приложения.' };
  if (!env.secure) return { state: 'insecure', message: 'Уведомления работают только по HTTPS (или на localhost). Открой сайт по защищённому адресу.' };
  // iOS/iPadOS: Web Push есть только у сайта, добавленного на экран «Домой» (iOS/iPadOS 16.4+), в обычной вкладке Safari его нет вовсе.
  if (env.platform === 'ios' && !env.standalone) {
    return { state: 'ios-install', message: 'На iPhone и iPad уведомления приходят только установленному сайту: в Safari нажми «Поделиться» → «На экран “Домой”», затем открой иконку и включи уведомления здесь.' };
  }
  if (!env.hasSW || !env.hasPush || !env.hasNotification) {
    return { state: 'unsupported', message: env.platform === 'ios' ? 'Для уведомлений нужен iOS/iPadOS 16.4 или новее.' : 'Этот браузер не поддерживает push-уведомления.' };
  }
  if (env.permission === 'denied') {
    return { state: 'denied', message: 'Уведомления для этого сайта заблокированы в настройках браузера. Разреши их в настройках сайта и обнови страницу.' };
  }
  return { state: 'ok', message: '' };
}

export function urlBase64ToUint8Array(base64) {
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, ch => ch.charCodeAt(0));
}

export function isStandalone(win = globalThis) {
  try { return !!(win.navigator?.standalone || win.matchMedia?.('(display-mode: standalone)').matches); } catch { return false; }
}
