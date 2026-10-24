import { h, icon } from '../../ui.js';
import { exceptions, loadAll } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded, formatDate, dayName, dayShort } from '../kit.js';
import { moscowToday, dateKey, parseDate } from '../../schedule-dates.js';

export async function mount(root, { signal }) {
  const filter = { scope: 'upcoming' };
  let data;
  async function refresh() { data = await loadAll({ signal }); draw(); }

  const sessionLabel = s => `${data.club.get(s.club_id)?.name ?? '?'} — ${dayShort(s.weekday)} ${s.start_time}–${s.end_time}, ${data.room.get(s.room_id)?.name ?? '?'}`;
  const sessionOptions = () => [...data.sessions].sort((a, b) => sessionLabel(a).localeCompare(sessionLabel(b), 'ru')).map(s => [s.id, sessionLabel(s)]);

  // Дата переносимого/отменяемого занятия должна приходиться на день недели занятия — иначе сервер ответит ошибкой; ловим заранее.
  function checkWeekday(values) {
    const session = data.session.get(values.session_id);
    const date = parseDate(values.original_date);
    if (!date) throw new Error('Укажи дату занятия.');
    if (session && (date.getDay() + 6) % 7 + 1 !== session.weekday) throw new Error(`Это занятие по дням «${dayName(session.weekday)}» — выбери подходящую дату.`);
  }

  async function open(kind, item) {
    if (!data.sessions.length) { await confirmDialog({ title: 'Нет занятий', message: 'Сначала добавь регулярное занятие в разделе «Занятия».', confirmLabel: 'Понятно', danger: false }); return; }
    const isMove = kind === 'moved';
    const fields = [
      { name: 'session_id', label: 'Занятие', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: sessionOptions() },
      { name: 'original_date', label: 'Какого числа (по расписанию)', type: 'date', required: true },
      ...(isMove ? [
        { name: 'new_date', label: 'Перенести на дату', type: 'date', required: true },
        { name: 'new_start_time', label: 'Новое начало', type: 'time', required: true },
        { name: 'new_end_time', label: 'Новый конец', type: 'time', required: true },
        { name: 'new_room_id', label: 'Аудитория', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: data.rooms.map(r => [r.id, r.name]) },
      ] : []),
      { name: 'comment', label: 'Комментарий для учеников', type: 'textarea', maxlength: 4000, hint: 'Увидят подписчики и все на странице кружка.' },
    ];
    const saved = await formDialog({
      title: item ? (isMove ? 'Изменить перенос' : 'Изменить отмену') : (isMove ? 'Перенести занятие' : 'Отменить занятие'),
      submitLabel: item ? 'Сохранить' : (isMove ? 'Перенести' : 'Отменить занятие'), danger: !isMove && !item,
      intro: item ? undefined : 'Подписчикам кружка уйдёт уведомление (если они его включили).',
      fields, initial: item ?? {},
      onSubmit: values => {
        checkWeekday(values);
        if (isMove && values.new_start_time >= values.new_end_time) throw new Error('Начало должно быть раньше конца.');
        if (item) {
          const patch = Object.fromEntries(Object.entries(values).filter(([k, v]) => v !== item[k]));
          return exceptions.update(item.id, { ...patch, type: kind });
        }
        return isMove ? exceptions.move(values) : exceptions.cancel(values);
      },
    });
    if (saved) await refresh();
  }
  async function remove(e) {
    const s = data.session.get(e.session_id);
    const ok = await confirmDialog({ title: 'Вернуть занятие в расписание?', message: `${s ? sessionLabel(s) : 'Занятие'}, ${formatDate(e.original_date)}: ${e.type === 'moved' ? 'перенос' : 'отмена'} будет удалён.`, confirmLabel: 'Удалить запись' });
    if (ok && await guarded(() => exceptions.remove(e.id), 'Запись удалена')) await refresh();
  }

  function draw() {
    const today = dateKey(moscowToday());
    const scope = h('select', { 'aria-label': 'Период' }, [['upcoming', 'Ближайшие и будущие'], ['all', 'Все, включая прошедшие']].map(([v, t]) => h('option', { value: v, selected: v === filter.scope }, t)));
    const host = h('div', {});
    const paint = () => {
      const rows = data.exceptions.filter(e => filter.scope === 'all' || (e.new_date && e.new_date >= today) || e.original_date >= today)
        .sort((a, b) => a.original_date.localeCompare(b.original_date));
      host.replaceChildren(dataTable({
        caption: 'Отмены и переносы', rows, empty: 'Отмен и переносов нет',
        columns: [
          { label: 'Дата', cell: e => h('span', { class: 'slot-time' }, formatDate(e.original_date)) },
          { label: 'Занятие', cell: e => { const s = data.session.get(e.session_id); return s ? h('strong', {}, sessionLabel(s)) : '—'; } },
          { label: 'Что', cell: e => h('span', { class: `badge badge--${e.type === 'moved' ? 'moved' : 'cancelled'}` }, e.type === 'moved' ? 'Перенос' : 'Отмена') },
          { label: 'Куда', cell: e => e.type === 'moved' ? `${formatDate(e.new_date)} ${e.new_start_time}–${e.new_end_time}, ${data.room.get(e.new_room_id)?.name ?? '?'}` : '—' },
          { label: 'Комментарий', cell: e => e.comment || '—' },
        ],
        actions: e => [actionButton('Изменить', 'edit', () => open(e.type, e)), actionButton('Удалить', 'trash', () => remove(e), 'btn--danger-text')],
      }));
    };
    scope.addEventListener('change', () => { filter.scope = scope.value; paint(); });
    root.replaceChildren(
      pageHeader('Отмены и переносы',
        h('button', { type: 'button', class: 'btn btn--outline-danger', onclick: () => open('cancelled') }, 'Отменить занятие'),
        h('button', { type: 'button', class: 'btn btn--filled', onclick: () => open('moved') }, icon('plus'), 'Перенести занятие')),
      h('div', { class: 'toolbar' }, h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Показать'), scope)),
      host);
    paint();
  }

  root.replaceChildren(pageHeader('Отмены и переносы'), loading());
  await refresh();
  root.querySelector('#view-title')?.focus({ preventScroll: true });
}
