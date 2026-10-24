// Подписка на уведомления о переносах/отменах конкретного кружка (Web Push + VAPID).
import { request } from './api.js';
import { h, icon, toast } from './ui.js';
import { pushAvailability, urlBase64ToUint8Array, isStandalone } from './push-support.js';

function environment() {
  return {
    native: !!window.Capacitor?.isNativePlatform?.(),
    secure: window.isSecureContext === true,
    hasSW: 'serviceWorker' in navigator,
    hasPush: 'PushManager' in window,
    hasNotification: 'Notification' in window,
    platform: window.ClubsTheme?.platform || 'desktop',
    standalone: isStandalone(window),
    permission: 'Notification' in window ? Notification.permission : 'default',
  };
}

async function registration() {
  return (await navigator.serviceWorker.getRegistration('/')) || navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(() => navigator.serviceWorker.ready);
}

async function currentSubscription() {
  const reg = await registration();
  return { reg, sub: await reg.pushManager.getSubscription() };
}

async function isSubscribed(clubId) {
  const { sub } = await currentSubscription();
  if (!sub) return false;
  const status = await request('/api/push/status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) });
  return status.all || status.club_ids.includes(clubId);
}

export async function subscribe(clubId) {
  // requestPermission обязан вызываться из обработчика клика (требование Safari/iOS)
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw Object.assign(new Error('Разрешение на уведомления не выдано.'), { code: 'permission' });
  const { publicKey } = await request('/api/push/vapid-public-key');
  const { reg, sub: existing } = await currentSubscription();
  const sub = existing || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  const json = sub.toJSON();
  await request('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys, club_id: clubId }) });
}

export async function unsubscribe(clubId) {
  const { sub } = await currentSubscription();
  if (!sub) return;
  const result = await request('/api/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint, club_id: clubId }) });
  if (result.remaining === 0) await sub.unsubscribe();
}

/** Рисует блок «Уведомления» внутри container. Ничего не ломает, если push недоступен — показывает причину. */
export async function mountClubPush(container, clubId) {
  const env = environment();
  const availability = pushAvailability(env);
  const title = h('h3', {}, 'Уведомления');
  const note = h('p', { class: 'field-hint', role: 'status' });
  const button = h('button', { type: 'button', class: 'btn btn--tonal' }, icon('bell'), h('span', {}, 'Уведомлять об изменениях'));
  const root = h('section', { class: 'card push-card', 'aria-labelledby': 'push-title' }, title, note, button);
  title.id = 'push-title';
  container.append(root);
  const label = text => { button.querySelector('span').textContent = text; };

  if (availability.state !== 'ok') {
    note.textContent = availability.message;
    button.hidden = availability.state !== 'ios-install';
    if (availability.state === 'ios-install') { button.replaceWith(h('a', { class: 'btn btn--tonal', href: '/install' }, 'Как установить на iPhone')); }
    return root;
  }
  note.textContent = 'Скажем, если занятие этого кружка отменят или перенесут.';
  let subscribed = false;
  try { subscribed = await isSubscribed(clubId); } catch { /* сервер без push или нет сети — кнопка всё равно доступна */ }
  const sync = () => { label(subscribed ? 'Отключить уведомления' : 'Уведомлять об изменениях'); button.setAttribute('aria-pressed', String(subscribed)); };
  sync();
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      if (subscribed) { await unsubscribe(clubId); subscribed = false; toast('Уведомления отключены'); }
      else { await subscribe(clubId); subscribed = true; toast('Готово: сообщим об отменах и переносах'); }
    } catch (error) {
      const denied = error.code === 'permission' || Notification.permission === 'denied';
      note.textContent = denied ? pushAvailability({ ...environment(), permission: 'denied' }).message : error.message || 'Не удалось изменить подписку.';
      toast(note.textContent, { kind: 'error' });
    } finally { button.disabled = false; sync(); }
  });
  return root;
}
