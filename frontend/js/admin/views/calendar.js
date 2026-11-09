import { h } from '../../ui.js';
import { request } from '../../api.js';
import { moscowToday, monday, dateKey, addDays, DAY_SHORT } from '../../schedule-dates.js';
import { roomLabel } from '../../public-display.js';
import { rooms, calendarMove } from '../api.js';
import { pageHeader, loading, formDialog } from '../kit.js';
export async function mount(root, { signal }) {
  let week = monday(moscowToday()), events = [], dragging = null, busy = false, epoch = 0;
  const rms = await rooms.list({ signal }); if (signal.aborted) return;
  const status = h('p', { role: 'status', class: 'field-hint' });
  async function move(event, target = event.date) {
    if (busy || signal.aborted) return;
    busy = true;
    try {
      const result = await formDialog({ title: 'Перенести одно занятие', intro: `${event.club_name} · ${event.date} ${event.start_time}–${event.end_time}. Меняется только эта дата, не шаблон недели. Пересечения проверяются сервером перед сохранением.`,
        initial: { new_date: target, new_start_time: event.start_time, new_end_time: event.end_time, new_room_id: event.room_ids?.[0] || event.room_id, comment: event.comment || '' },
        fields: [ { name: 'new_date', label: 'Новая дата', type: 'date', required: true }, { name: 'new_start_time', label: 'Начало', type: 'time', required: true },
          { name: 'new_end_time', label: 'Конец', type: 'time', required: true }, { name: 'new_room_id', label: 'Аудитория переноса', type: 'select', numeric: true, required: true, options: rms.map(r => [r.id, roomLabel(r)]) },
          { name: 'comment', label: 'Комментарий', maxlength: 500 } ],
        onSubmit: values => {
          if (values.new_start_time < '08:00' || values.new_end_time > '21:00') throw new Error('Занятия проводятся с 08:00 до 21:00');
          if (values.new_start_time >= values.new_end_time) throw new Error('Начало должно быть раньше конца');
          return calendarMove({ event_id: event.event_id, source_date: event.date, revision: event.revision,
            move: { type: 'moved', session_id: event.session_id, original_date: event.original_date || event.date, ...values } });
        } });
      if (result && !signal.aborted) { status.textContent = 'Занятие перенесено. Отмена — в журнале действий.'; await refresh(); }
    } finally { busy = false; dragging = null; }
  }
  const grid = h('div', { class: 'admin-calendar-grid', 'aria-label': 'Календарь занятий, понедельник — суббота' });
  const caption = h('span', { class: 'field-hint' });
  const date = h('input', { type: 'date', value: dateKey(week), 'aria-label': 'Дата недели календаря' });
  async function refresh() {
    const current = ++epoch; status.textContent = 'Загрузка…';
    try {
      const data = await request('/api/admin/calendar?week=' + dateKey(week), { signal, cache: 'no-store' });
      if (signal.aborted || current !== epoch) return;
      events = data.items; caption.textContent = dateKey(week) + ' — ' + dateKey(addDays(week, 5));
      grid.replaceChildren(...Array.from({ length: 6 }, (_, i) => {
        const key = dateKey(addDays(week, i));
        const day = h('section', { class: 'admin-calendar-day', dataset: { date: key }, 'aria-label': DAY_SHORT[i] + ', ' + key }, h('h2', {}, DAY_SHORT[i] + ' · ' + key.slice(8)));
        day.addEventListener('dragover', e => { if (dragging && !busy) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; day.classList.add('is-drop-target'); } });
        day.addEventListener('dragleave', e => { if (!day.contains(e.relatedTarget)) day.classList.remove('is-drop-target'); });
        day.addEventListener('drop', e => { e.preventDefault(); day.classList.remove('is-drop-target'); const event = dragging; dragging = null; if (event && !busy) void move(event, key); });
        const rows = events.filter(x => x.date === key).sort((a, b) => a.start_time.localeCompare(b.start_time));
        if (!rows.length) day.append(h('p', { class: 'field-hint' }, 'Занятий нет'));
        rows.forEach(event => {
          const canMove = event.status !== 'cancelled';
          const card = h('article', { class: 'admin-calendar-event', draggable: canMove, dataset: { event: event.event_id } },
            h('strong', {}, event.club_name), h('span', {}, `${event.start_time}–${event.end_time}`), h('span', {}, event.room_name),
            event.status === 'cancelled' && h('span', {}, 'Отменено'), event.status === 'moved' && h('span', {}, 'Перенесено'),
            canMove && h('button', { type: 'button', class: 'btn btn--small btn--tonal', onclick: () => move(event), 'aria-label': `Перенести ${event.club_name}, ${event.date}, ${event.start_time}` }, 'Перенести'));
          card.addEventListener('dragstart', e => { if (!canMove || busy) { e.preventDefault(); return; } dragging = event; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', event.event_id); });
          card.addEventListener('dragend', () => { dragging = null; grid.querySelectorAll('.is-drop-target').forEach(x => x.classList.remove('is-drop-target')); });
          day.append(card);
        });
        return day;
      })); status.textContent = 'Занятий: ' + events.length;
    } catch (e) { if (e.name !== 'AbortError' && !signal.aborted) status.textContent = e.message; }
  }
  date.addEventListener('change', () => { if (!date.value) return; const parsed = new Date(date.value + 'T12:00:00'); if (Number.isNaN(parsed.getTime())) return; week = monday(parsed); void refresh(); });
  root.replaceChildren(pageHeader('Календарь переносов', h('a', { class: 'btn', href: '#/sessions' }, 'К занятиям')),
    h('p', { class: 'field-hint' }, 'Перетащите карточку на нужный день и подтвердите время. На iPhone, с клавиатуры и экранным диктором используйте кнопку «Перенести». Сохранение защищено от устаревшего календаря.'),
    h('div', { class: 'toolbar' }, h('button', { type: 'button', class: 'btn', onclick: () => { week = addDays(week, -7); date.value = dateKey(week); void refresh(); } }, 'Предыдущая неделя'), date,
      h('button', { type: 'button', class: 'btn', onclick: () => { week = addDays(week, 7); date.value = dateKey(week); void refresh(); } }, 'Следующая неделя'), caption), status, grid);
  await refresh();
}
