import { h } from '../../ui.js';
import { imports, loadAll, periods } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded, dayName, WEEKDAY_OPTIONS } from '../kit.js';

export async function mount(root, { signal }) {
  let drafts = [], refs, academicPeriods = [], selected = null;
  async function refresh(id = selected?.id) {
    [drafts, refs, academicPeriods] = await Promise.all([imports.list({ signal }), loadAll({ signal }), periods.list({ signal })]);
    selected = drafts.find(d => d.id === id) || null;
    draw();
  }
  async function save(row, choice) {
    const decisions = (selected.decisions || []).filter(d => d.row !== row.row);
    decisions.push({ row: row.row, ...choice });
    const result = await guarded(() => imports.decisions(selected.id, decisions), 'Решение сохранено');
    if (result) await refresh(selected.id);
  }
  async function configure(row) {
    const initial = { club_name: row.club_name, weekday: row.weekday, start_time: row.start_time, end_time: row.end_time,
      ...((selected.decisions || []).find(d => d.row === row.row) || {}) };
    const suggestions = [
      ...(row.matching_club_ids || []).map(id => `кружок: ${refs.club.get(id)?.name || id}`),
      ...(row.matching_leader_ids || []).map(id => `руководитель: ${refs.leader.get(id)?.name || id}`),
      ...(row.matching_room_ids || []).map(id => { const r = refs.room.get(id); return `аудитория: ${r?.name || id}${r?.building ? ` · ${r.building}` : ''}`; }),
    ];
    const result = await formDialog({ title: `Строка ${row.row}: ${row.club_name}`, initial,
      intro: `В документе: ${dayName(row.weekday)} ${row.time_text}; ${row.leaders}; ${row.rooms}. ${suggestions.length ? `Возможные совпадения: ${suggestions.join('; ')}.` : ''} Уточните данные и связи.`,
      fields: [
        { name: 'club_name', label: 'Название из документа', required: true, maxlength: 120 },
        { name: 'weekday', label: 'День недели', type: 'select', numeric: true, required: true, options: WEEKDAY_OPTIONS },
        { name: 'start_time', label: 'Начало', type: 'time', required: true },
        { name: 'end_time', label: 'Конец', type: 'time', required: true },
        { name: 'club_id', label: 'Кружок', type: 'select', numeric: true, placeholder: 'Создать новый из названия', options: refs.clubs.map(c => [c.id, c.name]) },
        { name: 'category_id', label: 'Направление нового кружка', type: 'select', numeric: true, placeholder: 'Выбери…', options: refs.categories.map(c => [c.id, c.name]) },
        { name: 'leader_id', label: 'Основной руководитель нового кружка', type: 'select', numeric: true, placeholder: 'Выбери…', options: refs.leaders.map(l => [l.id, l.name]) },
        { name: 'leader_ids', label: 'Руководители занятия', type: 'multiselect', options: refs.leaders.map(l => [l.id, l.name]), hint: 'Если не выбраны, используются руководители кружка.' },
        { name: 'room_ids', label: 'Аудитории', type: 'multiselect', options: refs.rooms.map(r => [r.id, `${r.name}${r.building ? ` · ${r.building}` : ''}`]), hint: 'Выберите хотя бы одну аудиторию.' },
        { name: 'period_id', label: 'Учебный период', type: 'select', numeric: true, placeholder: 'Без периода', options: academicPeriods.map(p => [p.id, p.name]) },
        { name: 'repeat', label: 'Повторение', type: 'select', required: true, placeholder: 'Выберите повторение', options: [['weekly', 'Каждую неделю'], ['even', 'Чётные недели'], ['odd', 'Нечётные недели']] },
      ],
      onSubmit: values => {
        if (!values.room_ids.length) throw new Error('Выберите хотя бы одну аудиторию.');
        if (!values.club_id && (!values.category_id || !values.leader_id)) throw new Error('Для нового кружка выберите направление и основного руководителя.');
        if (['even', 'odd'].includes(values.repeat) && !values.period_id) throw new Error('Для чередования укажите учебный период.');
        return save(row, { ...values, action: 'create' });
      } });
    if (result) await refresh(selected?.id);
  }
  async function upload(file) {
    if (!file) return;
    if (file.size > 600000) { await confirmDialog({ title: 'Файл слишком большой', message: 'Допустимый размер — до 600 КБ.', confirmLabel: 'Понятно', danger: false }); return; }
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (const b of bytes) binary += String.fromCharCode(b);
    const result = await guarded(() => imports.create({ filename: file.name, content_base64: btoa(binary) }), 'Черновик создан');
    if (result) await refresh(result.id);
  }
  function draw() {
    const input = h('input', { type: 'file', accept: '.docx,.xlsx', 'aria-label': 'Файл расписания' });
    const uploadButton = h('button', { type: 'button', class: 'btn btn--filled', onclick: () => upload(input.files[0]) }, 'Создать черновик');
    const selector = h('select', { 'aria-label': 'Черновик' }, h('option', { value: '' }, 'Выберите черновик'),
      drafts.map(d => h('option', { value: String(d.id), selected: d.id === selected?.id }, `${d.filename} · ${d.status === 'published' ? 'опубликован' : 'черновик'}`)));
    selector.addEventListener('change', () => { selected = drafts.find(d => String(d.id) === selector.value) || null; draw(); });
    const content = [];
    if (selected) {
      const decisions = new Map((selected.decisions || []).map(d => [d.row, d]));
      content.push(h('p', {}, 'Для каждой строки выберите создание или пропуск. Аудитории и руководителей нужно заранее добавить в справочники.'),
        dataTable({ caption: 'Строки импорта', rows: selected.rows, empty: 'Строк нет', columns: [
          { label: 'Строка', cell: r => String(r.row) }, { label: 'Кружок', cell: r => r.club_name },
          { label: 'По документу', cell: r => `${dayName(r.weekday)} ${r.time_text}; ${r.leaders}; ${r.rooms}` },
          { label: 'Замечания', cell: r => r.issues.join('; ') || 'Проверьте данные' },
          { label: 'Решение', cell: r => decisions.get(r.row)?.action === 'skip' ? 'Пропустить' : decisions.has(r.row) ? 'Подготовлено' : 'Не выбрано' }],
        actions: r => selected.status !== 'draft' ? [] : [actionButton('Настроить', 'edit', () => configure(r)), actionButton('Пропустить', 'trash', () => save(r, { action: 'skip' }))] }));
      if (selected.status === 'draft') content.push(h('button', { type: 'button', class: 'btn btn--filled', onclick: async () => {
        if (await confirmDialog({ title: 'Опубликовать расписание?', message: 'Все выбранные строки будут повторно проверены. При ошибке ничего не сохранится.', confirmLabel: 'Опубликовать', danger: false })) {
          const result = await guarded(() => imports.publish(selected.id), 'Расписание опубликовано');
          if (result) await refresh(selected.id);
        }
      } }, 'Опубликовать подготовленные строки'));
    }
    root.replaceChildren(pageHeader('Импорт расписания'), h('p', {}, 'Файл DOCX или XLSX до 600 КБ. Сначала создаётся черновик — действующее расписание не меняется.'),
      h('div', { class: 'toolbar' }, input, uploadButton, selector), ...content);
  }
  root.replaceChildren(pageHeader('Импорт расписания'), loading());
  await refresh();
}
