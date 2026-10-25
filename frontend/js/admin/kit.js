// Набор мелких компонентов админки: формы в диалогах, подтверждения, таблицы, показ конфликтов расписания.
// Всё строится через h() (textContent) — разметка из данных сервера не интерпретируется.
import { h, icon, toast } from '../ui.js';
import { DAY_NAMES, DAY_SHORT } from '../schedule-dates.js';

export const dayName = n => DAY_NAMES[n - 1] ?? `день ${n}`;
export const dayShort = n => DAY_SHORT[n - 1] ?? String(n);
export const WEEKDAY_OPTIONS = DAY_NAMES.map((name, i) => [i + 1, name]);
export const formatDate = key => {
  const [y, m, d] = String(key).split('-');
  return y && m && d ? `${d}.${m}.${y}` : String(key ?? '');
};

const REASONS = { room: 'аудитория занята', leader: 'руководитель занят' };

/** Блок «Пересечения»: показывает, с чем именно конфликтует изменение (ответ 409 {conflicts:[…]}). */
export function conflictList(conflicts) {
  return h('div', { class: 'conflict-box', role: 'alert' },
    h('strong', {}, 'Это изменение пересекается с расписанием:'),
    h('ul', {}, conflicts.map(c => h('li', {},
      h('span', { class: 'conflict-title' }, `${c.club_name}, ${formatDate(c.date)} ${c.start_time}–${c.end_time}`),
      h('span', { class: 'conflict-meta' }, ` · ${c.room_name}, ${c.leader_name}`),
      h('span', { class: 'badge badge--cancelled' }, (c.reasons || []).map(r => REASONS[r] || r).join(', '))))));
}

function errorNode(error) {
  const detail = error?.detail;
  if (detail && Array.isArray(detail.conflicts)) return h('div', {}, h('p', { class: 'field-error' }, detail.message || 'Конфликт расписания.'), conflictList(detail.conflicts));
  return h('p', { class: 'field-error', role: 'alert' }, error?.message || 'Не удалось выполнить действие.');
}

function fieldControl(spec, value) {
  const id = `f-${spec.name}`;
  const common = { id, name: spec.name, required: !!spec.required, 'aria-describedby': `${id}-hint` };
  if (spec.type === 'select') {
    const select = h('select', common, spec.placeholder !== undefined && h('option', { value: '' }, spec.placeholder),
      spec.options.map(([v, label]) => h('option', { value: String(v), selected: String(v) === String(value ?? '') }, label)));
    return select;
  }
  if (spec.type === 'textarea') return h('textarea', { ...common, maxlength: spec.maxlength ?? 4000, rows: 4, value: value ?? '' });
  if (spec.type === 'checkbox') return h('input', { ...common, type: 'checkbox', checked: !!value });
  const attrs = { ...common, type: spec.type || 'text', value: value ?? '', autocomplete: 'off' };
  if (spec.maxlength) attrs.maxlength = spec.maxlength;
  if (spec.min !== undefined) attrs.min = spec.min;
  if (spec.max !== undefined) attrs.max = spec.max;
  return h('input', attrs);
}

function readForm(form, fields) {
  const out = {};
  for (const spec of fields) {
    const el = form.elements[spec.name];
    let value;
    if (spec.type === 'checkbox') value = el.checked;
    else if (spec.type === 'number' || spec.type === 'select' && spec.numeric) value = el.value === '' ? null : Number(el.value);
    else value = el.value.trim();
    out[spec.name] = value;
  }
  return out;
}

let openDialog = null;
function showDialog(dialog) {
  openDialog?.close();
  document.body.append(dialog);
  dialog.addEventListener('close', () => { dialog.remove(); if (openDialog === dialog) openDialog = null; }, { once: true });
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  openDialog = dialog;
  dialog.showModal();
}

/**
 * Диалог-форма. fields: [{name,label,type,required,options,numeric,hint,maxlength,placeholder}]; onSubmit(values) → Promise.
 * Пока запрос идёт, кнопка блокируется; ошибка (включая 409 с конфликтами) показывается внутри диалога, данные остаются.
 * Резолвится результатом onSubmit или null при отмене.
 */
export function formDialog({ title, fields, initial = {}, submitLabel = 'Сохранить', intro, onSubmit, danger = false }) {
  return new Promise(resolve => {
    let result = null;
    const feedback = h('div', { class: 'form-feedback', 'aria-live': 'polite' });
    const form = h('form', { class: 'form-grid', novalidate: true });
    for (const spec of fields) {
      const control = fieldControl(spec, initial[spec.name]);
      const label = spec.type === 'checkbox'
        ? h('label', { class: 'checkbox', for: `f-${spec.name}` }, control, spec.label)
        : h('label', { class: 'field', for: `f-${spec.name}` }, h('span', { class: 'field-label' }, spec.label + (spec.required ? ' *' : '')), control);
      form.append(label);
      if (spec.hint) form.append(h('p', { class: 'field-hint', id: `f-${spec.name}-hint` }, spec.hint));
    }
    const cancel = h('button', { type: 'button', class: 'btn btn--text' }, 'Отмена');
    const submit = h('button', { type: 'submit', class: `btn ${danger ? 'btn--danger' : 'btn--filled'}` }, submitLabel);
    const dialog = h('dialog', { class: 'sheet sheet--bottom', 'aria-labelledby': 'dlg-title' },
      h('div', { class: 'sheet-head' }, h('h2', { id: 'dlg-title' }, title),
        h('button', { type: 'button', class: 'btn btn--text btn--small', 'aria-label': 'Закрыть', onclick: () => dialog.close() }, icon('close'))),
      h('div', { class: 'sheet-body' }, intro && h('p', { class: 'field-hint' }, intro), form, feedback),
      h('div', { class: 'sheet-foot' }, cancel, submit));
    submit.setAttribute('form', 'dlg-form');
    form.id = 'dlg-form';
    cancel.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => resolve(result), { once: true });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      feedback.replaceChildren();
      for (const el of form.elements) el.removeAttribute?.('aria-invalid');
      const bad = [...form.elements].find(el => el.willValidate && !el.checkValidity());
      if (bad) {
        bad.setAttribute('aria-invalid', 'true');
        feedback.append(h('p', { class: 'field-error', role: 'alert' }, bad.validationMessage || 'Проверь поле.'));
        bad.focus();
        return;
      }
      submit.disabled = true;
      try {
        result = (await onSubmit(readForm(form, fields))) ?? true;
        dialog.close();
      } catch (error) {
        feedback.replaceChildren(errorNode(error));
        feedback.scrollIntoView({ block: 'nearest' });
        if (error?.status === 401) dialog.close();
      } finally { submit.disabled = false; }
    });
    showDialog(dialog);
    dialog.querySelector('input:not([type=checkbox]), select, textarea')?.focus();
  });
}

/** Подтверждение опасного действия. Резолвится true/false. */
export function confirmDialog({ title, message, confirmLabel = 'Удалить', danger = true }) {
  return new Promise(resolve => {
    let ok = false;
    const yes = h('button', { type: 'button', class: `btn ${danger ? 'btn--danger' : 'btn--filled'}`, onclick: () => { ok = true; dialog.close(); } }, confirmLabel);
    const no = h('button', { type: 'button', class: 'btn btn--text', onclick: () => dialog.close() }, 'Отмена');
    const dialog = h('dialog', { class: 'sheet', 'aria-labelledby': 'cf-title', role: 'alertdialog' },
      h('div', { class: 'sheet-head' }, h('h2', { id: 'cf-title' }, title)),
      h('div', { class: 'sheet-body' }, h('p', {}, message)),
      h('div', { class: 'sheet-foot' }, no, yes));
    dialog.addEventListener('close', () => resolve(ok), { once: true });
    showDialog(dialog);
    no.focus(); // по умолчанию — безопасная кнопка
  });
}

/** Таблица, на телефоне превращающаяся в карточки (CSS .cards). columns: [{label, cell(row)|key, class}]. */
export function dataTable({ columns, rows, actions, empty = 'Пока ничего нет.', caption }) {
  if (!rows.length) return h('div', { class: 'empty-state' }, h('strong', {}, empty));
  const head = h('tr', {}, columns.map(c => h('th', { scope: 'col' }, c.label)), actions && h('th', { scope: 'col' }, h('span', { class: 'visually-hidden' }, 'Действия')));
  const body = rows.map(row => h('tr', {},
    columns.map(c => h('td', { dataset: { label: c.label }, class: c.class }, typeof c.cell === 'function' ? c.cell(row) : row[c.key])),
    actions && h('td', { class: 'actions' }, actions(row))));
  return h('div', { class: 'table-wrap' }, h('table', { class: 'data cards' }, caption && h('caption', { class: 'visually-hidden' }, caption), h('thead', {}, head), h('tbody', {}, body)));
}

export const actionButton = (label, iconName, onclick, extra = '') =>
  h('button', { type: 'button', class: `btn btn--small btn--text ${extra}`.trim(), onclick, 'aria-label': label, title: label }, icon(iconName), h('span', { class: 'btn-label' }, label));

/** Запуск действия с единым показом ошибки через snackbar. */
export async function guarded(action, successMessage) {
  try {
    const result = await action();
    if (successMessage) toast(successMessage);
    return result ?? true;
  } catch (error) {
    if (error?.status !== 401) toast(error?.message || 'Не удалось выполнить действие.', { kind: 'error' });
    return false;
  }
}

export function pageHeader(title, ...actions) {
  return h('div', { class: 'admin-head' }, h('h1', { id: 'view-title', tabindex: -1 }, title), h('div', { class: 'admin-head-actions' }, actions));
}
export const loading = () => h('div', { class: 'skeleton-block', 'aria-busy': 'true' }, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
