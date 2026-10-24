import { h, icon } from '../../ui.js';
import { categories, leaders, rooms, loadAll } from '../api.js';
import { pageHeader, loading, dataTable, actionButton, formDialog, confirmDialog, guarded, secretDialog } from '../kit.js';
import { request } from '../../api.js';

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
  let access = new Map(); // leader_id → {has_access, issued_at}: доступ преподавателя (идентификатор T-…)
  const refresh = async () => {
    data = await loadAll({ signal });
    if (key === 'leaders') { try { access = new Map((await request('/api/admin/teachers', { signal })).map(t => [t.leader_id, t])); } catch { access = new Map(); } }
    draw();
  };
  const showToken = (r, verb) => secretDialog({ title: `Идентификатор: ${r.name}`, secret: r.token,
    message: `${verb}. Передайте его преподавателю: в приложении «Кружки» → «Я преподаю» → вставить идентификатор. Права: только просмотр своих кружков и отметка посещаемости.` });
  async function addTeacher() {
    let res = null;
    await formDialog({ title: 'Добавить преподавателя', submitLabel: 'Создать и выдать идентификатор',
      intro: 'Создаётся руководитель и одноразово показывается его идентификатор доступа (T-…).',
      fields: [{ name: 'name', label: 'ФИО', required: true, maxlength: 120 }, { name: 'position', label: 'Должность', maxlength: 300 }],
      onSubmit: async v => { res = await request('/api/admin/teachers', send('POST', v)); return res; } });
    if (res) { await showToken(res, 'Преподаватель добавлен'); await refresh(); }
  }
  async function grant(x) {
    const has = access.get(x.id)?.has_access;
    if (has && !await confirmDialog({ title: `Перевыпустить для «${x.name}»?`, message: 'Старый идентификатор и все его входы сразу перестанут работать.', confirmLabel: 'Перевыпустить' })) return;
    const r = await guarded(() => request(`/api/admin/leaders/${x.id}/access`, send('POST')));
    if (r) { await showToken(r, has ? 'Идентификатор перевыпущен' : 'Доступ выдан'); await refresh(); }
  }
  // перенос на новый телефон: одноразовый QR на 10 минут (старый телефон отключится после сканирования)
  async function transfer(x) {
    const r = await guarded(() => request(`/api/admin/leaders/${x.id}/transfer`, send('POST')));
    if (!r) return;
    let svg = '';
    try { if (!window.qrcode) await new Promise((ok, no) => { const sc = document.createElement('script'); sc.src = '/js/vendor/qrcode.js'; sc.onload = ok; sc.onerror = no; document.head.append(sc); }); const q = window.qrcode(0, 'M'); q.addData(r.code); q.make(); svg = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true }); } catch { /* без QR — только код */ }
    await secretDialog({ title: `Перенос на новый телефон: ${r.name}`, secret: r.code, qrSvg: svg,
      message: 'На новом телефоне: «Войти» → «Я преподаю» → «Сканировать QR переноса». Код действует 10 минут и один раз; после сканирования старый телефон выйдет из аккаунта.' });
  }
  async function revoke(x) {
    if (await confirmDialog({ title: `Отозвать доступ «${x.name}»?`, message: 'Преподаватель сразу потеряет доступ к отметкам.', confirmLabel: 'Отозвать' })
      && await guarded(() => request(`/api/admin/leaders/${x.id}/access`, send('DELETE')), 'Доступ отозван')) await refresh();
  }

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
      pageHeader('Справочники', key === 'leaders' && h('button', { type: 'button', class: 'btn btn--tonal', 'data-add-teacher': '', onclick: addTeacher }, icon('plus'), 'Добавить преподавателя'),
        h('button', { type: 'button', class: 'btn btn--filled', onclick: () => edit(null) }, icon('plus'), `Добавить ${cfg.one}`)),
      tabs,
      dataTable({
        caption: cfg.title, rows: data[key], empty: `${cfg.title}: пока пусто`,
        columns: [...cfg.columns, { label: 'Используется', cell: x => String(cfg.usedBy(data, x)) },
          ...(key === 'leaders' ? [{ label: 'Доступ', cell: x => access.get(x.id)?.has_access
            ? h('span', { class: 'badge badge--ok', title: `выдан ${new Date(access.get(x.id).issued_at).toLocaleString('ru-RU')}` }, 'выдан') : h('span', { class: 'badge' }, 'нет') }] : [])],
        actions: x => [...(key === 'leaders' ? [actionButton(access.get(x.id)?.has_access ? 'Перевыпустить' : 'Выдать доступ', 'key', () => grant(x)),
            ...(access.get(x.id)?.has_access ? [actionButton('QR переноса', 'key', () => transfer(x)), actionButton('Отозвать', 'close', () => revoke(x), 'btn--danger-text')] : [])] : []),
          actionButton('Изменить', 'edit', () => edit(x)), actionButton('Удалить', 'trash', () => remove(x), 'btn--danger-text')],
      }));
    // цвет метки задаётся через CSSOM (CSP запрещает style="…" в разметке)
    for (const dot of root.querySelectorAll('.dot[data-color]')) dot.style.setProperty('--dot', dot.dataset.color);
  }

  root.replaceChildren(pageHeader('Справочники'), loading());
  await refresh();
  root.querySelector('#view-title')?.focus({ preventScroll: true });
}
