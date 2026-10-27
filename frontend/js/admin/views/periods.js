import { h } from '../../ui.js';
import { periods } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded, formatDate } from '../kit.js';

export async function mount(root, { signal }) {
  let data = [];
  async function refresh() { data = await periods.list({ signal }); draw(); }
  async function edit(item) {
    const result = await formDialog({ title: item ? 'Изменить период' : 'Новый учебный период', initial: item ?? {},
      intro: 'Укажите понедельник недели, которую колледж считает чётной.',
      fields: [{ name: 'name', label: 'Название', required: true }, { name: 'start_date', label: 'Начало', type: 'date', required: true },
        { name: 'end_date', label: 'Окончание', type: 'date', required: true }, { name: 'even_week_start', label: 'Понедельник чётной недели', type: 'date', required: true }],
      onSubmit: values => item ? periods.update(item.id, values) : periods.create(values) });
    if (result) await refresh();
  }
  async function days(item) {
    const values = await periods.days(item.id);
    const text = values.length ? values.map(x => `${formatDate(x.date)} — ${x.reason || 'без занятий'}`).join('\n') : 'Пока нет неучебных дней.';
    if (await confirmDialog({ title: `Неучебные дни: ${item.name}`, message: text, confirmLabel: 'Добавить день', danger: false })) {
      const result = await formDialog({ title: 'Неучебный день', fields: [{ name: 'date', label: 'Дата', type: 'date', required: true }, { name: 'reason', label: 'Причина' }], onSubmit: v => periods.addDay(item.id, v) });
      if (result) await refresh();
    }
  }
  async function removeDay(item) {
    const values = await periods.days(item.id);
    if (!values.length) { await confirmDialog({ title: 'Неучебных дней нет', message: item.name, confirmLabel: 'Понятно', danger: false }); return; }
    const result = await formDialog({ title: 'Вернуть учебный день', fields: [{ name: 'day_id', label: 'Дата', type: 'select', numeric: true, required: true,
      placeholder: 'Выбери…', options: values.map(d => [d.id, `${formatDate(d.date)} · ${d.reason || 'без занятий'}`]) }],
      intro: 'Перед восстановлением приложение проверит конфликты расписания.', onSubmit: v => periods.removeDay(item.id, v.day_id) });
    if (result) await refresh();
  }
  async function addRange(item) {
    const result = await formDialog({ title: 'Каникулы или праздничные дни', fields: [
      { name: 'start_date', label: 'Начало', type: 'date', required: true }, { name: 'end_date', label: 'Конец', type: 'date', required: true },
      { name: 'reason', label: 'Причина' }], onSubmit: v => periods.addDays(item.id, v) });
    if (result) await refresh();
  }
  function draw() {
    root.replaceChildren(pageHeader('Учебные периоды', h('button', { type: 'button', class: 'btn btn--filled', onclick: () => edit() }, 'Добавить период')),
      h('p', {}, 'Чётность считается от указанной опорной недели. Изменения проверяются на конфликты и существующие переносы.'),
      dataTable({ caption: 'Учебные периоды', rows: data, empty: 'Периодов пока нет', columns: [
        { label: 'Название', cell: x => x.name }, { label: 'Начало', cell: x => formatDate(x.start_date) },
        { label: 'Конец', cell: x => formatDate(x.end_date) }, { label: 'Чётная неделя', cell: x => formatDate(x.even_week_start) }],
      actions: x => [actionButton('Неучебные дни', 'calendar', () => days(x)), actionButton('Добавить каникулы', 'calendar', () => addRange(x)), actionButton('Вернуть учебный день', 'calendar', () => removeDay(x)), actionButton('Изменить', 'edit', () => edit(x)),
        actionButton('Удалить', 'trash', async () => { if (await confirmDialog({ title: 'Удалить период?', message: x.name }) && await guarded(() => periods.remove(x.id))) await refresh(); })] }));
  }
  root.replaceChildren(pageHeader('Учебные периоды'), loading());
  await refresh();
}
