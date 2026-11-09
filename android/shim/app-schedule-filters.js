import { h } from './ui.js';
import { bindSheetDismiss } from './sheet-gesture.js';

const groups = [
  ['category_id', 'Направление'], ['weekday', 'День'], ['leader_id', 'Руководитель'], ['room_id', 'Аудитория'],
];

export function openScheduleFilters({ fields, changeFilters, resetFilters, trigger }) {
  if (document.getElementById('itc-filter-sheet')) return;
  const body = h('div', { class: 'sheet-body itc-fsheet-body' });
  const close = h('button', { type: 'button', class: 'glass-action' }, 'Закрыть');
  const reset = h('button', { type: 'button', class: 'text-button' }, 'Сбросить');
  const apply = h('button', { type: 'button', class: 'btn btn--primary' }, 'Показать');
  const title = h('h2', { id: 'itc-filter-title' }, 'Фильтры');
  const sheet = h('dialog', {
    id: 'itc-filter-sheet', class: 'sheet sheet--bottom itc-filter-sheet', 'aria-labelledby': title.id, dataset: { swipeDismiss: 'filters' },
  }, h('div', { class: 'sheet-head' }, title, h('div', { class: 'filter-sheet-actions' }, reset, close)),
  body, h('div', { class: 'sheet-foot' }, apply));
  const choices = new Map();
  for (const [key, label] of groups) {
    const options = [...fields[key].options];
    const radios = options.map(option => h('input', {
      type: 'radio', name: `itc-filter-${key}`, value: option.value, checked: fields[key].value === option.value,
    }));
    choices.set(key, radios);
    body.append(h('section', { class: 'itc-fgroup' }, h('h3', {}, label),
      h('div', { class: 'itc-fchips', role: 'radiogroup', 'aria-label': label }, radios.map((radio, index) =>
        h('label', { class: 'itc-fchip glass-action' }, radio, h('span', {}, options[index].value ? options[index].textContent : 'Все'))))));
  }
  close.addEventListener('click', () => sheet.close());
  reset.addEventListener('click', () => { resetFilters(); sheet.close(); });
  apply.addEventListener('click', () => {
    for (const [key, radios] of choices) fields[key].value = radios.find(radio => radio.checked)?.value || '';
    changeFilters();
    sheet.close();
  });
  sheet.addEventListener('close', () => {
    trigger.setAttribute('aria-expanded', 'false');
    sheet.remove();
    trigger.focus({ preventScroll: true });
  }, { once: true });
  bindSheetDismiss(sheet, { scrollBody: () => body });
  trigger.setAttribute('aria-expanded', 'true');
  trigger.setAttribute('aria-controls', sheet.id);
  document.body.append(sheet);
  sheet.showModal();
  close.focus({ preventScroll: true });
}
