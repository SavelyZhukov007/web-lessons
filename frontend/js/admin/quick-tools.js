import { h } from '../ui.js';
import { request } from '../api.js';
import { confirmDialog, guarded } from './kit.js';

export function mountQuickTools(routes, slot, refresh) {
  let dialog;
  const open = () => {
    if (dialog?.open) return;
    dialog = h('dialog', { class: 'admin-command', 'aria-labelledby': 'command-title' });
    const list = h('div', { class: 'command-results', id: 'command-results' });
    const input = h('input', { type: 'search', 'aria-label': 'Поиск раздела или команды', placeholder: 'Найти раздел…', dataset: { nativeSearch: '' }, 'aria-controls': 'command-results' });
    const paint = () => {
      const q = input.value.trim().toLocaleLowerCase('ru-RU');
      list.replaceChildren(...Object.entries(routes).filter(([, r]) => r.title.toLocaleLowerCase('ru-RU').includes(q)).map(([key, r]) =>
        h('a', { class: 'btn btn--tonal', href: '#/' + key, onclick: () => dialog.close() }, r.title)));
      if (!list.children.length) list.append(h('p', {}, 'Ничего не найдено'));
    };
    input.addEventListener('input', paint);
    input.addEventListener('keydown', event => { if (event.key === 'ArrowDown') { event.preventDefault(); list.querySelector('a')?.focus(); } if (event.key === 'Enter') list.querySelector('a')?.click(); });
    dialog.append(h('h2', { id: 'command-title' }, 'Быстрый переход'), input, list,
      h('button', { type: 'button', class: 'btn', onclick: () => dialog.close() }, 'Закрыть'));
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    document.body.append(dialog); paint(); dialog.showModal(); input.focus();
  };
  slot.prepend(h('button', { type: 'button', class: 'btn btn--tonal', 'aria-label': 'Быстрый переход, Control K или Command K', onclick: open }, 'Поиск · ⌘/Ctrl K'));
  window.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && (event.key.toLowerCase() === 'k' || event.code === 'KeyK')) { event.preventDefault(); if (!document.querySelector('dialog[open]')) open(); }
  });
  const status = h('aside', { class: 'admin-undo', role: 'status', 'aria-live': 'polite', hidden: true });
  document.querySelector('#admin-main').before(status);
  let epoch = 0;
  window.addEventListener('admin:mutation', async ({ detail }) => {
    const current = ++epoch;
    try {
      const data = await request('/api/admin/actions?request_id=' + encodeURIComponent(detail.request_id), { cache: 'no-store' });
      const action = data.items?.find(x => x.rollback_available);
      if (!action || current !== epoch) return;
      status.replaceChildren(h('span', {}, action.label || 'Изменение сохранено'), h('button', { type: 'button', class: 'btn btn--tonal', onclick: async event => {
        const button = event.currentTarget;
        if (!await confirmDialog({ title: 'Отменить изменение?', message: 'Данные будут восстановлены, если после этого их не меняли. Уже отправленные уведомления вернуть нельзя.', confirmLabel: 'Отменить изменение', danger: false })) return;
        button.disabled = true;
        const result = await guarded(() => request('/api/admin/actions/' + action.id + '/undo', { method: 'POST' }), 'Изменение отменено');
        if (result) { status.hidden = true; refresh(); } else button.disabled = false;
      } }, 'Отменить изменение'), h('button', { type: 'button', class: 'btn', 'aria-label': 'Скрыть уведомление об отмене', onclick: () => { status.hidden = true; } }, 'Закрыть'));
      status.hidden = false;
    } catch { /* a successful mutation must not become a client error if the ledger request fails */ }
  });
}
