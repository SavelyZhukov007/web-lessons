import { h, icon } from './ui.js';
import { hasTapFeedback, setTapFeedback, tapFeedbackEnabled } from './interaction-feedback.js';
import { bindGlassIndicator } from './glass.js';

function toggle(title, hint, checked, onChange) {
  const box = h('input', { type: 'checkbox', role: 'switch', checked });
  box.addEventListener('change', () => onChange(box.checked));
  return h('label', { class: 'preference-toggle' },
    h('span', {}, h('span', {}, title), hint && h('small', {}, hint)), box);
}

function section(title, hint, open, ...rows) {
  return h('details', { class: 'preferences-section', open },
    h('summary', { class: 'glass-trigger' }, h('span', {}, h('b', {}, title), h('small', {}, hint)), icon('right')),
    h('div', { class: 'preference-rows' }, ...rows));
}

export function interfaceSettings(theme, signal) {
  const prefs = theme.get();
  const option = (key, title, hint) => toggle(title, hint, prefs[key], checked => theme.set({ [key]: checked }));
  const modes = h('div', { class: 'segmented glass-tabs', role: 'radiogroup', 'aria-label': 'Перелистывание расписания' });
  for (const [value, title] of [['centered', 'Лента'], ['week', 'По неделям']]) {
    const input = h('input', { type: 'radio', name: 'day-navigation', value, checked: prefs.dayNavigation === value });
    input.addEventListener('change', () => theme.set({ dayNavigation: value }));
    modes.append(h('label', {}, input, h('span', {}, title)));
  }
  bindGlassIndicator(modes, () => modes.querySelector('input:checked')?.closest('label'), { signal });
  const panel = h('div', { class: 'interface-preferences' },
    section('Расписание', 'Дни, свайпы и ближайшее занятие', true,
      h('div', { class: 'preference-mode' }, h('b', {}, 'Перелистывание расписания'), modes,
        h('p', { class: 'field-hint' }, 'Лента держит выбранный день в центре. В режиме «По неделям» свайп по полосе переключает всю неделю.')),
      option('daySwipe', 'Свайп по занятиям', 'Сменить день жестом по списку'),
      option('showDayMarks', 'Отметки на полосе дней', 'Точки показывают занятия, отмены и переносы'),
      option('showNextClass', 'Ближайшее занятие', 'Подсказка над списком «Моих кружков»')),
    section('Карточки занятий', 'Плотность списка и видимые детали', false,
      option('compactSchedule', 'Компактный список', 'Меньше расстояние между занятиями'),
      option('showRoom', 'Аудитории'), option('showLeader', 'Руководители'), option('showEndTime', 'Время окончания'),
      h('p', { class: 'field-hint' }, 'В подробностях занятия всегда видны все данные.')),
    section('Эффекты и доступность', 'Движение, прозрачность и отклик', false,
      option('reduceMotion', 'Меньше движения', 'Короткие переходы и переключение дней без анимации'),
      option('solidGlass', 'Непрозрачные панели', 'Стеклянные панели со сплошной заливкой'),
      hasTapFeedback() && toggle('Вибрация при нажатии', 'Тактильный отклик при выборе дня и переключении недели', tapFeedbackEnabled(), setTapFeedback)));
  return panel;
}
