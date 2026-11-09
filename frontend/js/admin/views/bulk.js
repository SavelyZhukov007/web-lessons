import { h } from '../../ui.js';
import { request } from '../../api.js';
import { moscowToday, dateKey } from '../../schedule-dates.js';
import { roomLabel } from '../../public-display.js';
import { loadAll } from '../api.js';
import { pageHeader, loading, confirmDialog, guarded, dayShort } from '../kit.js';
export async function mount(root, { signal }) {
  root.replaceChildren(pageHeader('Пакетные изменения'), loading());
  const data = await loadAll({ signal });
  if (signal.aborted) return;
  const selected = new Set();
  const today = dateKey(moscowToday());
  const action = h('select', { 'aria-label': 'Действие' }, h('option', { value: 'cancel' }, 'Отменить занятия в даты (каникулы)'), h('option', { value: 'delete' }, 'Удалить выбранные занятия целиком'));
  const from = h('input', { type: 'date', value: today, required: true, 'aria-label': 'Начало отмен' });
  const to = h('input', { type: 'date', value: today, required: true, 'aria-label': 'Конец отмен' });
  const comment = h('input', { maxlength: 500, placeholder: 'Причина отмены', 'aria-label': 'Причина отмены' });
  const notify = h('input', { type: 'checkbox' });
  const search = h('input', { type: 'search', placeholder: 'Кружок, корпус или аудитория', 'aria-label': 'Найти занятия для выбора' });
  const list = h('fieldset', { class: 'bulk-choices' });
  const count = h('p', { role: 'status', class: 'field-hint' }, 'Выбрано: 0 / 100');
  const previewHost = h('section', { class: 'bulk-preview', 'aria-label': 'Предварительный просмотр' });
  let previewEpoch = 0;
  const cancelPreview = () => { previewEpoch++; previewHost.replaceChildren(); };
  let visible = [];
  const title = s => `${data.club.get(s.club_id)?.name || 'Занятие'} · ${s.one_off_date || dayShort(s.weekday)} ${s.start_time}–${s.end_time} · ${(s.room_ids?.length ? s.room_ids : [s.room_id]).map(id => roomLabel(data.room.get(id))).join(', ')}`;
  const paint = () => {
    const q = search.value.trim().toLocaleLowerCase('ru-RU'); visible = data.sessions.filter(s => title(s).toLocaleLowerCase('ru-RU').includes(q));
    list.replaceChildren(h('legend', {}, 'Занятия для изменения'), ...visible.map(s => {
      const input = h('input', { type: 'checkbox', checked: selected.has(s.id), 'aria-label': title(s) });
      input.addEventListener('change', () => { if (input.checked && selected.size >= 100) { input.checked = false; count.textContent = 'Не больше 100 занятий за один раз'; return; }
        input.checked ? selected.add(s.id) : selected.delete(s.id); count.textContent = `Выбрано: ${selected.size} / 100`; cancelPreview(); });
      return h('label', { class: 'bulk-choice' }, input, h('span', {}, title(s)));
    }));
  };
  search.addEventListener('input', paint);
  [action, from, to, comment, notify].forEach(x => x.addEventListener('change', cancelPreview));
  const preview = h('button', { type: 'button', class: 'btn btn--filled', onclick: async () => {
    if (!selected.size) { count.textContent = 'Сначала выберите занятия'; return; }
    const body = { action: action.value, session_ids: [...selected], date_from: from.value || null, date_to: to.value || null, comment: comment.value, notify: notify.checked };
    const current = ++previewEpoch;
    preview.disabled = true;
    try {
      const result = await request('/api/admin/bulk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
      if (signal.aborted || current !== previewEpoch) return;
      const apply = h('button', { type: 'button', class: 'btn btn--filled', disabled: !result.count, onclick: async () => {
        if (!await confirmDialog({ title: body.action === 'delete' ? 'Удалить занятия?' : 'Отменить занятия?', message: `Будут изменены записи: ${result.count}. ${body.action === 'delete' ? 'Удалятся все связанные отмены и переносы.' : 'Повторяющийся шаблон останется; отменятся только указанные даты, включая перенесённые сюда занятия.'} ${body.notify ? 'Будут отправлены уведомления.' : 'Без рассылки уведомлений.'}`, confirmLabel: 'Применить' })) return;
        apply.disabled = true;
        const saved = await guarded(async () => {
          const { bulk } = await import('../api.js'); return bulk({ ...body, preview: false, confirmation: result.confirmation });
        }, 'Пакетное изменение сохранено');
        if (saved) { selected.clear(); await mount(root, { signal }); } else apply.disabled = false;
      } }, 'Подтвердить пакетное изменение');
      previewHost.replaceChildren(h('h2', {}, 'Изменений: ' + result.count), h('ul', {}, result.items.map(x => h('li', {}, x.title + (x.date ? ' · ' + x.date : '') + (x.exceptions ? ` · связанных правок: ${x.exceptions}` : '')))), apply);
      previewHost.scrollIntoView({ block: 'nearest' });
    } catch (e) { if (e.name !== 'AbortError') previewHost.replaceChildren(h('p', { role: 'alert' }, e.message)); }
    finally { preview.disabled = false; }
  } }, 'Предварительный просмотр');
  root.replaceChildren(pageHeader('Пакетные изменения', h('a', { class: 'btn', href: '#/sessions' }, 'К занятиям')),
    h('p', {}, 'Сначала выберите записи, затем проверьте состав изменений. Сохранение атомарное; отмена доступна в журнале.'),
    h('div', { class: 'toolbar' }, search, h('button', { type: 'button', class: 'btn btn--tonal', onclick: () => {
      const all = visible.length && visible.every(s => selected.has(s.id));
      if (!all && new Set([...selected, ...visible.map(s => s.id)]).size > 100) { count.textContent = 'Сузьте поиск: максимум 100 занятий'; return; }
      visible.forEach(s => all ? selected.delete(s.id) : selected.add(s.id)); count.textContent = `Выбрано: ${selected.size} / 100`; cancelPreview(); paint();
    } }, 'Выбрать / снять найденные')), count, list,
    h('div', { class: 'toolbar' }, action, from, to, comment, h('label', { class: 'bulk-choice' }, notify, 'Отправить уведомления об отменах')), preview, previewHost);
  paint();
}
