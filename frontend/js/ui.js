// Мелкие общие помощники UI: hyperscript без innerHTML, snackbar, ripple (Android), фокус.
import { icon } from './icons.js';

/** h('div', {class:'x', onclick(){}}, 'text', child) — только textContent/узлы, XSS через разметку невозможен. */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in el && key !== 'list' && key !== 'form') { try { el[key] = value; } catch { el.setAttribute(key, value); } }
    else el.setAttribute(key, value === true ? '' : value);
  }
  append(el, children);
  return el;
}
function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}
export { icon };

let host;
/** Короткое уведомление внизу экрана (role=status). kind: 'info' | 'error'. */
export function toast(message, { kind = 'info', timeout = 5000, action } = {}) {
  if (!host) {
    host = h('div', { class: 'snackbar-host', role: 'status', 'aria-live': 'polite' });
    document.body.append(host);
  }
  const node = h('div', { class: `snackbar${kind === 'error' ? ' snackbar--error' : ''}` }, h('span', {}, message));
  if (action) node.append(h('button', { type: 'button', onclick: () => { action.run(); node.remove(); } }, action.label));
  host.append(node);
  const timer = setTimeout(() => node.remove(), kind === 'error' ? Math.max(timeout, 8000) : timeout);
  node.addEventListener('remove', () => clearTimeout(timer));
  return node;
}

/** Material-ripple для кнопок на Android. Включается только при class="platform-android" и без reduced-motion. */
export function installRipple() {
  if (!document.documentElement.classList.contains('platform-android')) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.addEventListener('pointerdown', event => {
    const target = event.target.closest?.('.btn, .campus-page button, .settings-button');
    if (!target || target.disabled) return;
    const rect = target.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const dot = h('span', { class: 'ripple', 'aria-hidden': 'true' });
    dot.style.width = dot.style.height = `${size}px`;
    dot.style.left = `${event.clientX - rect.left - size / 2}px`;
    dot.style.top = `${event.clientY - rect.top - size / 2}px`;
    target.style.position ||= 'relative';
    target.append(dot);
    dot.addEventListener('animationend', () => dot.remove(), { once: true });
  }, { passive: true });
}
// Cached public data must be distinguishable from a confirmed server response.
const offlineSources = new Map();
let offlineNotice;
window.addEventListener('public:cache-state', ({ detail }) => {
  if (detail.offline) offlineSources.set(detail.path, detail.savedAt);
  else offlineSources.delete(detail.path);
  if (!offlineNotice && !offlineSources.size) return;
  if (!offlineNotice) {
    offlineNotice = document.createElement('p');
    offlineNotice.className = 'error-state';
    offlineNotice.setAttribute('role', 'status');
    document.body.prepend(offlineNotice);
  }
  offlineNotice.hidden = offlineSources.size === 0;
  if (offlineSources.size) {
    const date = new Date([...offlineSources.values()].sort()[0]);
    offlineNotice.textContent = `Нет сети. Показаны сохранённые данные от ${date.toLocaleString('ru-RU')}. Изменения расписания могли ещё не загрузиться.`;
  }
});
