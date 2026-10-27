import { h, icon } from '../../ui.js';
import { clubs, loadAll } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded } from '../kit.js';

export async function mount(root, { signal }) {
  const filter = { q: '', category: '', state: '' };
  let data;
  async function refresh() { data = await loadAll({ signal }); draw(); }

  function fields() {
    return [
      { name: 'name', label: 'Название', required: true, maxlength: 120 },
      { name: 'description', label: 'Описание', type: 'textarea', maxlength: 4000 },
      { name: 'category_id', label: 'Направление', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: data.categories.map(c => [c.id, c.name]) },
      { name: 'leader_id', label: 'Руководитель', type: 'select', numeric: true, required: true, placeholder: 'Выбери…', options: data.leaders.map(l => [l.id, l.name]) },
      { name: 'leader_ids', label: 'Дополнительные руководители', type: 'multiselect', options: data.leaders.map(l => [l.id, l.name]), hint: 'На компьютере удерживайте Ctrl для выбора нескольких; основной руководитель добавляется автоматически.' },
      { name: 'is_active', label: 'Показывать на сайте', type: 'checkbox' },
    ];
  }
  async function edit(club) {
    if (!data.categories.length || !data.leaders.length) {
      await confirmDialog({ title: 'Сначала справочники', message: 'Для кружка нужны хотя бы одно направление и один руководитель — добавь их в разделе «Справочники».', confirmLabel: 'Понятно', danger: false });
      return;
    }
    const saved = await formDialog({
      title: club ? 'Изменить кружок' : 'Новый кружок', fields: fields(), initial: club ? { ...club, leader_ids: (club.leader_ids || []).filter(id => id !== club.leader_id) } : { is_active: true },
      onSubmit: values => club ? clubs.update(club.id, values) : clubs.create(values),
    });
    if (saved) { await refresh(); }
  }
  async function remove(club) {
    const count = data.sessions.filter(s => s.club_id === club.id).length;
    const ok = await confirmDialog({ title: `Удалить «${club.name}»?`, message: count ? `Вместе с кружком будут удалены его занятия (${count}), отмены и переносы. Это нельзя отменить.` : 'Это нельзя отменить.' });
    if (ok && await guarded(() => clubs.remove(club.id), 'Кружок удалён')) await refresh();
  }
  async function toggle(club) {
    if (await guarded(() => clubs.update(club.id, { is_active: !club.is_active }), club.is_active ? 'Кружок скрыт с сайта' : 'Кружок показан на сайте')) await refresh();
  }

  function draw() {
    const search = h('input', { type: 'search', placeholder: 'Поиск по названию', value: filter.q, 'aria-label': 'Поиск кружков', maxlength: 200 });
    search.addEventListener('input', () => { filter.q = search.value; drawTable(); });
    const category = h('select', { 'aria-label': 'Направление' }, h('option', { value: '' }, 'Все направления'),
      data.categories.map(c => h('option', { value: String(c.id), selected: String(c.id) === filter.category }, c.name)));
    category.addEventListener('change', () => { filter.category = category.value; drawTable(); });
    const state = h('select', { 'aria-label': 'Статус' }, [['', 'Любой статус'], ['active', 'Показаны'], ['hidden', 'Скрыты']].map(([v, t]) => h('option', { value: v, selected: v === filter.state }, t)));
    state.addEventListener('change', () => { filter.state = state.value; drawTable(); });
    const tableHost = h('div', {});
    function drawTable() {
      const q2 = filter.q.toLocaleLowerCase('ru');
      const list = data.clubs.filter(c => (!q2 || `${c.name} ${c.description}`.toLocaleLowerCase('ru').includes(q2))
        && (!filter.category || String(c.category_id) === filter.category) && (!filter.state || (filter.state === 'active') === c.is_active));
      tableHost.replaceChildren(dataTable({
        caption: 'Кружки', rows: list, empty: data.clubs.length ? 'По фильтру ничего не найдено' : 'Кружков пока нет',
        columns: [
          { label: 'Название', cell: c => h('strong', {}, c.name) },
          { label: 'Направление', cell: c => data.cat.get(c.category_id)?.name ?? '—' },
          { label: 'Руководитель', cell: c => data.leader.get(c.leader_id)?.name ?? '—' },
          { label: 'Занятий', cell: c => String(data.sessions.filter(s => s.club_id === c.id).length) },
          { label: 'Статус', cell: c => h('span', { class: `badge ${c.is_active ? 'badge--ok' : ''}` }, c.is_active ? 'Показан' : 'Скрыт') },
        ],
        actions: c => [actionButton('Изменить', 'edit', () => edit(c)), actionButton(c.is_active ? 'Скрыть' : 'Показать', 'list', () => toggle(c)), actionButton('Удалить', 'trash', () => remove(c), 'btn--danger-text')],
      }));
    }
    root.replaceChildren(
      pageHeader('Кружки', h('button', { type: 'button', class: 'btn btn--filled', onclick: () => edit(null) }, icon('plus'), 'Добавить кружок')),
      h('div', { class: 'toolbar' }, h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Поиск'), search),
        h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Направление'), category),
        h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Статус'), state)),
      tableHost);
    drawTable();
  }

  root.replaceChildren(pageHeader('Кружки'), loading());
  await refresh();
  root.querySelector('#view-title')?.focus({ preventScroll: true });
}
