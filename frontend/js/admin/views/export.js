import { h } from '../../ui.js';
import { request } from '../../api.js';
import { moscowToday, dateKey, monday as weekMonday, addDays } from '../../schedule-dates.js';
import { roomLabel } from '../../public-display.js';
import { rooms } from '../api.js';
import { pageHeader, loading, dataTable } from '../kit.js';
export async function mount(root, { signal }) {
  root.replaceChildren(pageHeader('Экспорт и печать'), loading());
  const rms = await rooms.list({ signal }); if (signal.aborted) return;
  const monday = weekMonday(moscowToday());
  const from = h('input', { type: 'date', value: dateKey(monday), 'aria-label': 'Выгрузка с даты' });
  const to = h('input', { type: 'date', value: dateKey(addDays(monday, 5)), 'aria-label': 'Выгрузка по дату' });
  const building = h('select', { 'aria-label': 'Корпус выгрузки' }, h('option', { value: '' }, 'Все корпуса'), [...new Set(rms.map(r => r.building).filter(Boolean))].sort().map(x => h('option', { value: x }, x)));
  const room = h('select', { 'aria-label': 'Аудитория выгрузки' }, h('option', { value: '' }, 'Все аудитории'), rms.map(r => h('option', { value: r.id }, roomLabel(r))));
  const host = h('div', { class: 'admin-export-preview' });
  let controller, epoch = 0, loaded = '';
  const query = () => new URLSearchParams({ date_from: from.value, date_to: to.value, building: building.value, ...(room.value ? { room_id: room.value } : {}) }).toString();
  const print = h('button', { type: 'button', class: 'btn btn--tonal', disabled: true, onclick: () => window.print() }, 'Печать выбранного');
  const status = h('p', { role: 'status', class: 'field-hint' });
  const show = async () => {
    const current = ++epoch; controller?.abort(); controller = new AbortController();
    print.disabled = true; status.textContent = 'Загрузка…';
    try {
      const key = query(), data = await request('/api/admin/export?' + key, { signal: controller.signal, cache: 'no-store' });
      if (signal.aborted || current !== epoch) return;
      loaded = key; host.replaceChildren(h('h2', {}, `Расписание ${from.value} — ${to.value} (МСК)`), dataTable({ caption: 'Расписание для выгрузки', rows: data.rows, empty: 'Занятий нет', columns: data.headers.map((label, i) => ({ label, cell: row => row[i] })) }));
      print.disabled = false; status.textContent = 'Строк: ' + data.rows.length;
    } catch (e) { if (e.name !== 'AbortError' && current === epoch) status.textContent = e.message; }
  };
  signal.addEventListener('abort', () => controller?.abort(), { once: true });
  const download = format => h('button', { type: 'button', class: 'btn btn--filled', onclick: async event => {
    const button = event.currentTarget; button.disabled = true;
    try {
      const blob = await request('/api/admin/export?' + query() + '&format=' + format, { responseType: 'blob', signal, timeout: 30000 });
      if (signal.aborted) return;
      const url = URL.createObjectURL(blob), link = h('a', { href: url, download: 'kipclub-' + from.value + '.' + format });
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = 'Файл ' + format.toUpperCase() + ' готов';
    } catch (e) { if (e.name !== 'AbortError') status.textContent = e.message; }
    finally { button.disabled = false; }
  } }, format.toUpperCase());
  [from, to, building, room].forEach(x => x.addEventListener('change', () => { print.disabled = loaded !== query(); status.textContent = 'Фильтры изменены — обновите предпросмотр'; }));
  root.replaceChildren(pageHeader('Экспорт и печать', h('a', { class: 'btn', href: '#/sessions' }, 'К занятиям')),
    h('div', { class: 'toolbar export-controls' }, from, to, building, room, h('button', { type: 'button', class: 'btn btn--tonal', onclick: show }, 'Предпросмотр'), download('xlsx'), download('pdf'), print), status, host);
  await show();
}
