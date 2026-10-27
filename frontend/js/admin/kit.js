// Набор мелких компонентов админки: формы в диалогах, подтверждения, таблицы, показ конфликтов расписания.
// Всё строится через h() (textContent) — разметка из данных сервера не интерпретируется.
import { h, icon, toast } from '../ui.js';
import { DAY_NAMES, DAY_SHORT } from '../schedule-dates.js';
import { calendarDate as formatDate } from '../public-display.js';
import { readDraft, writeDraft, clearDraft, markUnsaved } from '../draft-state.js';
export { formatDate };

export const dayName = n => DAY_NAMES[n - 1] ?? `день ${n}`;
export const dayShort = n => DAY_SHORT[n - 1] ?? String(n);
export const WEEKDAY_OPTIONS = DAY_NAMES.map((name, i) => [i + 1, name]);

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
  const common = { id, name: spec.name, required: !!spec.required, 'aria-describedby': spec.hint ? `${id}-hint` : undefined };
  if (spec.type === 'select') {
    const select = h('select', common, spec.placeholder !== undefined && h('option', { value: '' }, spec.placeholder),
      spec.options.map(([v, label]) => h('option', { value: String(v), selected: String(v) === String(value ?? '') }, label)));
    return select;
  }
  if (spec.type === 'multiselect') return h('select', { ...common, multiple: true, size: Math.min(5, Math.max(2, spec.options.length)) },
    spec.options.map(([v, label]) => h('option', { value: String(v), selected: (value || []).map(String).includes(String(v)) }, label)));
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
    if (spec.type === 'multiselect') value = [...el.selectedOptions].map(o => Number(o.value));
    else if (spec.type === 'checkbox') value = el.checked;
    else if (spec.type === 'number' || spec.type === 'select' && spec.numeric) value = el.value === '' ? null : Number(el.value);
    else value = el.value.trim();
    out[spec.name] = value;
  }
  return out;
}

let openDialog = null;
function showDialog(dialog) {
  const opener = document.activeElement;
  openDialog?.close();
  document.body.append(dialog);
  dialog.addEventListener('close', () => { dialog.remove(); if (openDialog === dialog) openDialog = null; if (opener?.isConnected) opener.focus(); }, { once: true });
  dialog.addEventListener('click', event => { if (event.target === dialog && dialog.dataset.busy !== 'true') dialog.close(); });
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
    let submitting = false;
    let keepDraft = false;
    const feedback = h('div', { class: 'form-feedback', 'aria-live': 'polite' });
    const form = h('form', { class: 'form-grid', novalidate: true });
    const canStore = !fields.some(spec => spec.type === 'password');
    const draftKey = `form:${title}:${JSON.stringify(fields.map(spec => [spec.name, initial[spec.name] ?? null]))}`;
    const draft = canStore ? readDraft(draftKey) : null;
    for (const spec of fields) {
      const control = fieldControl(spec, draft && Object.hasOwn(draft, spec.name) ? draft[spec.name] : initial[spec.name]);
      const label = spec.type === 'checkbox'
        ? h('label', { class: 'checkbox', for: `f-${spec.name}` }, control, spec.label)
        : h('label', { class: 'field', for: `f-${spec.name}` }, h('span', { class: 'field-label' }, spec.label + (spec.required ? ' *' : '')), control);
      form.append(label);
      if (spec.hint) form.append(h('p', { class: 'field-hint', id: `f-${spec.name}-hint` }, spec.hint));
    }
    const initialValues = Object.fromEntries(fields.map(spec => [spec.name, spec.type === 'multiselect' ? (initial[spec.name] || []) : spec.type === 'checkbox' ? !!initial[spec.name] : spec.numeric || spec.type === 'number' ? (initial[spec.name] ?? null) : String(initial[spec.name] ?? '').trim()]));
    const preserve = () => {
      const values = readForm(form, fields);
      const dirty = JSON.stringify(values) !== JSON.stringify(initialValues);
      markUnsaved(form, dirty);
      if (canStore) { if (dirty) writeDraft(draftKey, values); else clearDraft(draftKey); }
    };
    form.addEventListener('input', preserve);
    form.addEventListener('change', preserve);
    if (draft) markUnsaved(form, true);
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
    dialog.addEventListener('cancel', event => { if (submitting) event.preventDefault(); });
    dialog.addEventListener('close', () => { if (canStore && !keepDraft) clearDraft(draftKey); resolve(result); }, { once: true });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (submitting) return;
      feedback.replaceChildren();
      for (const el of form.elements) el.removeAttribute?.('aria-invalid');
      const bad = [...form.elements].find(el => el.willValidate && !el.checkValidity());
      if (bad) {
        bad.setAttribute('aria-invalid', 'true');
        feedback.append(h('p', { class: 'field-error', role: 'alert' }, bad.validationMessage || 'Проверь поле.'));
        bad.focus();
        return;
      }
      submitting = true;
      dialog.dataset.busy = 'true';
      submit.disabled = true;
      cancel.disabled = true;
      dialog.querySelector('[aria-label="Закрыть"]').disabled = true;
      form.inert = true;
      preserve();
      try {
        result = (await onSubmit(readForm(form, fields))) ?? true;
        dialog.close();
      } catch (error) {
        feedback.replaceChildren(errorNode(error));
        feedback.scrollIntoView({ block: 'nearest' });
        if (error?.status === 401) { keepDraft = true; dialog.close(); }
      } finally {
        submitting = false; dialog.dataset.busy = 'false'; submit.disabled = false; cancel.disabled = false; form.inert = false;
        dialog.querySelector('[aria-label="Закрыть"]').disabled = false;
      }
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
