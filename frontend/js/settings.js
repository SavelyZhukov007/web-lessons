// Tiny eager chrome; settings/notification forms are parsed only when opened.
import { h, icon, toast, installRipple } from './ui.js';
import { mountGlassEverywhere } from './glass.js';
import './modal-scroll-lock.js'; // existing owner-reviewed lock remains unchanged
import './log-collector.js';
let panel;
async function open(opener, notifications = false) {
  opener?.setAttribute('aria-busy', 'true');
  try {
    panel ||= import('./settings-panel.js').catch(error => { panel = null; throw error; });
    const module = await panel;
    (notifications ? module.openNotifications : module.openSettings)(opener);
  } catch { toast('Не удалось открыть настройки. Проверьте подключение и попробуйте ещё раз.'); }
  finally { opener?.removeAttribute('aria-busy'); }
}
function mount() {
  if (!window.ClubsTheme) return;
  installRipple(); mountGlassEverywhere();
  if (document.querySelector('[data-settings-button]')) return;
  const button = h('button', { type: 'button', class: 'settings-button', 'aria-label': 'Настройки', 'aria-haspopup': 'dialog', dataset: { settingsButton: '' } }, icon('gear'));
  button.addEventListener('click', () => open(button));
  const header = document.querySelector('[data-settings-slot]') || document.querySelector('.campus-header');
  if (header && document.body.classList.contains('schedule-page') && !window.ItcPwa && !window.Capacitor?.isNativePlatform?.()) {
    const bell = h('button', { type: 'button', class: 'settings-button', id: 'itc-notify-open', 'aria-label': 'Уведомления', 'aria-haspopup': 'dialog' }, icon('bell'));
    bell.addEventListener('click', () => open(bell, true)); header.append(bell);
  }
  if (header) header.append(button); else document.body.prepend(button);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
window.ClubsSettings = { open: () => open(document.activeElement) };
