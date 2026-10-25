import { h, icon } from '../../ui.js';
import { categories, leaders, rooms, loadAll } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded } from '../kit.js';

const send = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });

const SECTIONS = {
  categories: {
    title: 'Направления', one: 'направление', defaults: { color: '#2563eb' }, api: categories, usedBy: (d, x) => d.clubs.filter(c => c.category_id === x.id).length, usedWord: 'кружков',
    fields: [{ name: 'name', label: 'Название', required: true, maxlength: 120 }, { name: 'color', label: 'Цвет метки', type: 'color', required: true, hint: 'Цветная метка направления на сайте.' }],
    columns: [{ label: 'Название', cell: x => h('strong', {}, x.name) }, { label: 'Цвет', cell: x => x.color ? h('span', { class: 'color-chip' }, h('i', { class: 'dot', dataset: { color: x.color } }), x.color) : '—' }],
  },
  leaders: {
    title: 'Руководители', one: 'руководителя', api: leaders, usedBy: (d, x) => d.clubs.filter(c => c.leader_id === x.id).length, usedWord: 'кружков',
    fields: [{ name: 'name', label: 'Имя', required: true, maxlength: 120 }, { name: 'position', label: 'Должность', maxlength: 300 }, { name: 'contact', label: 'Контакт', maxlength: 300 }],
    columns: [{ label: 'Имя', cell: x => h('strong', {}, x.name) }, { label: 'Должность', cell: x => x.position || '—' }, { label: 'Контакт', cell: x => x.contact || '—' }],
  },
  rooms: {
    title: 'Аудитории', one: 'аудиторию', api: rooms, usedBy: (d, x) => d.sessions.filter(s => s.room_id === x.id).length, usedWord: 'занятий',
    fields: [{ name: 'name', label: 'Номер / название', required: true, maxlength: 120 }, { name: 'building', label: 'Корпус', maxlength: 300 }, { name: 'capacity', label: 'Вместимость', type: 'number', required: true, min: 1, max: 10000 }],
    columns: [{ label: 'Аудитория', cell: x => h('strong', {}, x.name) }, { label: 'Корпус', cell: x => x.building || '—' }, { label: 'Мест', cell: x => String(x.capacity) }],
  },
};

export async function mount(root, { signal, param }) {
  const key = SECTIONS[param] ? param : 'categories';
  const cfg = SECTIONS[key];
  let data;
  const refresh = async () => {
    data = await loadAll({ signal });
    draw();
  };
  async function edit(item) {
    const saved = await formDialog({
      title: item ? `Изменить: ${cfg.one}` : `Добавить ${cfg.one}`, fields: cfg.fields, initial: item ?? cfg.defaults ?? {},
      onSubmit: values => {
        return item ? cfg.api.update(item.id, values) : cfg.api.create(values);
      },
    });
    if (saved) await refresh();
  }
  async function remove(item) {
    const used = cfg.usedBy(data, item);
    if (used) {
      await confirmDialog({ title: 'Удалить нельзя', message: `«${item.name}» используется (${used} ${cfg.usedWord}). Сначала перенеси их в другое место.`, confirmLabel: 'Понятно', danger: false });
      return;
    }
    if (await confirmDialog({ title: `Удалить «${item.name}»?`, message: 'Это нельзя отменить.' }) && await guarded(() => cfg.api.remove(item.id), 'Удалено')) await refresh();
  }

  function draw() {
    const tabs = h('div', { class: 'segmented admin-tabs', role: 'tablist', 'aria-label': 'Справочники' },
      Object.entries(SECTIONS).map(([k, c]) => h('a', { role: 'tab', href: `#/reference/${k}`, 'aria-selected': String(k === key), class: k === key ? 'is-current' : '' }, c.title)));
    root.replaceChildren(
      pageHeader('Справочники', h('button', { type: 'button', class: 'btn btn--filled', onclick: () => edit(null) }, icon('plus'), `Добавить ${cfg.one}`)),
      tabs,
      dataTable({
        caption: cfg.title, rows: data[key], empty: `${cfg.title}: пока пусто`,
        columns: [...cfg.columns, { label: 'Используется', cell: x => String(cfg.usedBy(data, x)) }],
        actions: x => [actionButton('Изменить', 'edit', () => edit(x)), actionButton('Удалить', 'trash', () => remove(x), 'btn--danger-text')],
      }));
    // цвет метки задаётся через CSSOM (CSP запрещает style="…" в разметке)
    for (const dot of root.querySelectorAll('.dot[data-color]')) dot.style.setProperty('--dot', dot.dataset.color);
  }

  root.replaceChildren(pageHeader('Справочники'), loading());
  await refresh();
  root.querySelector('#view-title')?.focus({ preventScroll: true });
}
