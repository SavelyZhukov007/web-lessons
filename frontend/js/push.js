// Подписка на уведомления о переносах/отменах конкретного кружка (Web Push + VAPID).
import { request } from './api.js';
import { h, icon, toast } from './ui.js';
import { pushAvailability, urlBase64ToUint8Array, isStandalone } from './push-support.js';

const post = (action, data) => request('/api/push/' + action, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
});
const preferenceLabels = { cancellations: 'Отмены занятий', moves: 'Переносы занятий', announcements: 'Объявления от администрации' };

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
  const status = await post('status', { endpoint: sub.endpoint });
  return status.all || status.club_ids.includes(clubId);
}

async function subscriptionFromGesture() {
  // requestPermission обязан вызываться из обработчика клика (требование Safari/iOS)
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw Object.assign(new Error('Разрешение на уведомления не выдано.'), { code: 'permission' });
  const { publicKey } = await request('/api/push/vapid-public-key');
  const { reg, sub: existing } = await currentSubscription();
  const sub = existing || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  return sub.toJSON();
}

export async function subscribe(clubId) {
  const { endpoint, keys } = await subscriptionFromGesture();
  await post('subscribe', { endpoint, keys, club_id: clubId });
}

export async function unsubscribe(clubId) {
  const { sub } = await currentSubscription();
  if (!sub) return;
  const result = await post('unsubscribe', { endpoint: sub.endpoint, club_id: clubId });
  if (result.remaining === 0) await sub.unsubscribe();
}

export function webNotificationPreferences() {
  const note = h('p', { class: 'field-hint', role: 'status' });
  const controls = h('div', {});
  const root = h('div', {}, note, controls);
  const env = environment();
  const availability = pushAvailability(env);
  if (availability.state !== 'ok') {
    note.textContent = availability.message;
    if (availability.state === 'ios-install') controls.append(h('a', { class: 'btn btn--tonal', href: '/install' }, 'Как установить на iPhone'));
    return root;
  }

  function render(endpoint, status) {
    note.textContent = 'Выберите, какие уведомления получать. Звук и вибрация зависят от настроек браузера и устройства.';
    const fields = Object.entries(preferenceLabels).map(([key, label]) => {
      const box = h('input', { type: 'checkbox', role: 'switch', checked: status[key] !== false });
      box.addEventListener('change', async () => {
        box.disabled = true;
        try {
          const result = await post('preferences', { endpoint, [key]: box.checked });
          if (!result.updated) throw new Error('Подписка изменилась. Откройте уведомления снова.');
          try { localStorage.setItem('itc.pwa.' + key, box.checked ? '1' : '0'); } catch { /* Safari private storage */ }
        } catch (e) { box.checked = !box.checked; note.textContent = e.message || 'Не удалось сохранить настройку.'; }
        finally { box.disabled = false; }
      });
      return h('label', { class: 'preference-toggle' }, h('span', {}, label), box);
    });
    controls.replaceChildren(...fields, h('p', { class: 'field-hint' }, 'Подписки на изменения отдельных кружков можно настроить в их карточках.'));
    import('./schedule-notification-form.js').then(m=>m.mountScheduleNotificationForm(controls,{load:()=>post('schedule-settings/read',{endpoint}),save:v=>post('schedule-settings',{endpoint,...v})})).catch(()=>{});
  }

  function offerAnnouncements() {
    note.textContent = 'Общие объявления можно включить сразу. Чтобы следить за отменами и переносами, подпишитесь на нужные кружки в каталоге.';
    const enable = h('button', { type: 'button', class: 'btn btn--tonal' }, 'Включить объявления');
    controls.replaceChildren(enable);
    enable.addEventListener('click', async () => {
      enable.disabled = true;
      try {
        const { endpoint, keys } = await subscriptionFromGesture();
        const status = await post('sync', { endpoint, keys, club_ids: [], announcements: true, cancellations: true, moves: true });
        render(endpoint, status);
      } catch (e) {
        note.textContent = pushAvailability(environment()).message || e.message || 'Не удалось включить уведомления.';
        enable.disabled = false;
      }
    });
  }

  note.textContent = 'Проверяем подписку…';
  currentSubscription().then(async ({ sub }) => {
    if (sub) {
      const status = await post('status', { endpoint: sub.endpoint });
      if (status.general || status.all || status.club_ids.length) { render(sub.endpoint, status); return; }
    }
    offerAnnouncements();
  }).catch(() => { note.textContent = 'Не удалось проверить подписку. Проверьте соединение и откройте окно снова.'; });
  return root;
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
