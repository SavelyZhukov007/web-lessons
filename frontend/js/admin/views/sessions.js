import { h, icon } from '../../ui.js';
import { roomLabel } from '../../public-display.js';
import { parseDate } from '../../schedule-dates.js';
import { sessions, loadAll } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded, formatDate, dayName, dayShort, WEEKDAY_OPTIONS } from '../kit.js';

export async function mount(root, { signal }) {
  const filter = { club: '', day: '' };
  let data;
  async function refresh() { data = await loadAll({ signal }); draw(); }

  async function edit(session, oneTime = false) {
    if (!data.clubs.length || !data.rooms.length) {
      await confirmDialog({ title: 'Не хватает данных', message: 'Для занятия нужны кружок и аудитория.', confirmLabel: 'Понятно', danger: false });
      return;
    }
    const single = oneTime || !!session?.one_off_date;
    const saved = await formDialog({
      title: session ? 'Изменить занятие' : single ? 'Разовое занятие' : 'Новое занятие',
      intro: single ? 'Это занятие состоится один раз в выбранную дату.' : 'Занятие будет повторяться каждую неделю. Конфликты проверяются для расписания целиком.',
      initial: session ?? { weekday: 1, start_time: '15:00', end_time: '16:00' },
      fields: [
        { name: 'club_id', label: 'Кружок', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: data.clubs.map(c => [c.id, c.name]) },
        { name: 'room_id', label: 'Аудитория', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: data.rooms.map(r => [r.id, roomLabel(r)]) },
        ...(single ? [{ name: 'one_off_date', label: 'Дата занятия', type: 'date', required: true }] : [{ name: 'weekday', label: 'День недели', type: 'select', numeric: true, required: true, options: WEEKDAY_OPTIONS }]),
        { name: 'start_time', label: 'Начало', type: 'time', required: true },
        { name: 'end_time', label: 'Конец', type: 'time', required: true },
      ],
      onSubmit: values => {
        if (values.start_time >= values.end_time) throw new Error('Начало должно быть раньше конца.');
        if (single) {
          const date = parseDate(values.one_off_date);
          if (!date || date.getDay() === 0) throw new Error('Выберите дату с понедельника по субботу.');
          values.weekday = date.getDay();
        }
        return session ? sessions.update(session.id, values) : sessions.create(values);
      },
    });
    if (saved) await refresh();
  }
  async function remove(session) {
    const club = data.club.get(session.club_id);
    const n = data.exceptions.filter(e => e.session_id === session.id).length;
    const ok = await confirmDialog({ title: 'Удалить занятие?', message: `${club?.name ?? 'Занятие'}, ${dayName(session.weekday)} ${session.start_time}–${session.end_time}.${n ? ` Будут удалены связанные отмены и переносы (${n}).` : ''}` });
    if (ok && await guarded(() => sessions.remove(session.id), 'Занятие удалено')) await refresh();
  }

  function draw() {
    const clubSel = h('select', { 'aria-label': 'Кружок' }, h('option', { value: '' }, 'Все кружки'), data.clubs.map(c => h('option', { value: String(c.id), selected: String(c.id) === filter.club }, c.name)));
    const daySel = h('select', { 'aria-label': 'День' }, h('option', { value: '' }, 'Все дни'), WEEKDAY_OPTIONS.map(([v, t]) => h('option', { value: String(v), selected: String(v) === filter.day }, t)));
    const host = h('div', {});
    const paint = () => {
      const rows = data.sessions.filter(s => (!filter.club || String(s.club_id) === filter.club) && (!filter.day || String(s.weekday) === filter.day));
      host.replaceChildren(dataTable({
        caption: 'Регулярные занятия', rows, empty: data.sessions.length ? 'По фильтру ничего не найдено' : 'Занятий пока нет',
        columns: [
          { label: 'День', cell: s => h('span', {}, s.one_off_date ? `Разово: ${formatDate(s.one_off_date)}` : dayShort(s.weekday)) },
          { label: 'Время', cell: s => h('span', { class: 'slot-time' }, `${s.start_time}–${s.end_time}`) },
          { label: 'Кружок', cell: s => h('strong', {}, data.club.get(s.club_id)?.name ?? '—') },
          { label: 'Аудитория', cell: s => roomLabel(data.room.get(s.room_id), '—') },
          { label: 'Руководитель', cell: s => data.leader.get(data.club.get(s.club_id)?.leader_id)?.name ?? '—' },
        ],
        actions: s => [actionButton('Изменить', 'edit', () => edit(s)), actionButton('Удалить', 'trash', () => remove(s), 'btn--danger-text')],
      }));
    };
    clubSel.addEventListener('change', () => { filter.club = clubSel.value; paint(); });
    daySel.addEventListener('change', () => { filter.day = daySel.value; paint(); });
    root.replaceChildren(
      pageHeader('Занятия', h('button', { type: 'button', class: 'btn btn--filled', onclick: () => edit(null) }, icon('plus'), 'Добавить занятие'),
        h('button', { type: 'button', class: 'btn btn--tonal', onclick: () => edit(null, true) }, 'Разовое занятие')),
      h('div', { class: 'toolbar' }, h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Кружок'), clubSel), h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'День'), daySel)),
      host);
    paint();
  }

  root.replaceChildren(pageHeader('Занятия'), loading());
  await refresh();
  root.querySelector('#view-title')?.focus({ preventScroll: true });
}
