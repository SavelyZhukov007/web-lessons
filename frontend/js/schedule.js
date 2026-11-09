import { campusTourLink } from './campus-tour.js';
import { markLiveCard, favoriteControls } from './personal-schedule.js';
import { DAY_NAMES, parseDate, dateKey, addDays, formatDate, minutes, eventGroups, scheduleLocation, movedFromSlot } from './schedule-dates.js';
import { currentStudyDay, mountScheduleUi } from './schedule-ui.js';
import { eventShareControls } from './schedule-share.js';
import { clubColor } from './event-colors.js';
import { icon } from './icons.js';
import { eventRoom } from './public-display.js';
import { runCascade } from './skeleton-cascade.js';
import { prefersReducedMotion } from './motion-preferences.js';

const $ = selector => document.querySelector(selector);
const content = $('#content');
const mobile = window.matchMedia('(max-width: 999px)');
const state = { ...scheduleLocation(location.search, currentStudyDay()), view: 'grid', events: [], phase: 'loading', error: '' };
const statusNames = { scheduled: 'По расписанию', moved: 'Перенос', cancelled: 'Отменено' };
const rooms = new Map();
let activeCascade = null;

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function visibleDays() {
  const weekday = $('#weekday').value;
  return weekday ? [Number(weekday) - 1] : [0, 1, 2, 3, 4, 5];
}

// «Перенесено»: перенесённое занятие оставляет в старом слоте приглушённую карточку со ссылкой «Актуальное время»
function ghostEvents(events) {
  return events.filter(movedFromSlot)
    .map(e => ({ ...e, ghost: true, moved: e, date: e.original_date,
      start_time: e.original_start_time || e.start_time, end_time: e.original_end_time || e.end_time }));
}

function ghostCard(ghost, compact = false) {
  const e = ghost.moved, nd = parseDate(e.date);
  const box = node('div', `calendar-event itc-ghost${compact ? ' compact' : ''}`);
  box.setAttribute('role', 'group');
  box.setAttribute('aria-label', `${e.club_name}: перенесено на ${formatDate(nd)}, ${e.start_time}`);
  const time = node('span', 'event-time itc-ghost-time');
  time.append(node('s', '', `${ghost.start_time}–${ghost.end_time}`));
  const go = node('button', 'itc-ghost-link', `Актуальное время: ${formatDate(nd, { weekday: 'short', day: 'numeric', month: 'long' })}, ${e.start_time}`);
  go.type = 'button';
  go.addEventListener('click', () => ui.jumpTo(e));
  box.append(time, node('strong', 'event-name', e.club_name), node('span', 'event-badge', 'Перенесено'), go);
  return box;
}

function details(event) {
  const target = $('#event-details');
  target.replaceChildren();
  target.append(node('p', `event-badge ${event.status}`, statusNames[event.status]));
  const title = node('h2', '', event.club_name);
  title.id = 'event-title';
  target.append(title);
  const info = node('dl', 'event-facts');
  const facts = [
    ['Когда', `${formatDate(parseDate(event.date), { year: 'numeric' })}, ${event.start_time}–${event.end_time}`],
    ['Аудитория', eventRoom(event, rooms)], ['Руководитель', (event.leader_names || [event.leader_name]).join(', ')], ['Направление', event.category_name],
  ];
  if (event.status === 'moved' && parseDate(event.original_date)) facts.push(['Исходная дата', formatDate(parseDate(event.original_date), { year: 'numeric' })]);
  for (const [label, value] of facts) info.append(node('dt', '', label), node('dd', '', value));
  target.append(info, campusTourLink(), favoriteControls(event));
  if (event.comment) target.append(node('p', 'event-comment', event.comment));
  const link = node('a', 'club-link', 'О кружке');
  link.append(icon('arrow'));
  link.href = `/club.html?id=${event.club_id}`;
  target.append(eventShareControls(event, link));
  if (!$('#event-dialog').open) $('#event-dialog').showModal();
}

function eventCard(event, compact = false) {
  if (event.ghost) return ghostCard(event, compact);
  const button = node('button', `calendar-event ${event.status}${event.status !== 'scheduled' ? ' has-status' : ''}${compact ? ' compact' : ''}`);
  button.type = 'button';
  button.dataset.eventId = event.event_id;
  const color = clubColor(event.club_id, event.category_color, event.category_name);
  button.style.setProperty('--event-color', color);
  button.setAttribute('aria-label', `${event.club_name}. ${formatDate(parseDate(event.date))}, ${event.start_time}–${event.end_time}. ${eventRoom(event, rooms)}. ${(event.leader_names || [event.leader_name]).join(', ')}. ${statusNames[event.status]}. Открыть подробности.`);
  const time = node('span', 'event-time');
  time.append(node('span', 'event-start', event.start_time), node('span', 'time-divider', '–'), node('span', 'event-end', event.end_time));
  button.append(time);
  button.append(node('strong', 'event-name', event.club_name), node('span', 'event-room', eventRoom(event, rooms)), node('span', 'event-leader', (event.leader_names || [event.leader_name]).join(', ')));
  if (event.status !== 'scheduled') button.append(node('span', 'event-badge', statusNames[event.status]));
  button.append(icon('right', 'event-affordance'));
  markLiveCard(button,event);
  button.addEventListener('click', () => details(event));
  return button;
}

function openEventGroup(events) {
  const target = $('#event-details');
  target.replaceChildren();
  const heading = node('h2', '', 'Занятия в это время');
  heading.id = 'event-title';
  target.append(heading, node('p', 'parallel-dialog-date', formatDate(parseDate(events[0].date), { year: 'numeric' })));
  const list = node('div', 'parallel-dialog-list');
  for (const event of events) {
    const button = node('button', 'parallel-dialog-item');
    button.type = 'button';
    button.style.setProperty('--event-color', clubColor(event.club_id, event.category_color, event.category_name));
    button.append(node('span', 'parallel-dialog-time', `${event.start_time}–${event.end_time}`),
      node('strong', '', event.club_name), node('span', 'parallel-dialog-room', eventRoom(event, rooms)));
    if (event.ghost) {
      const nd = parseDate(event.moved.date);
      button.classList.add('itc-ghost');
      button.append(node('span', 'event-badge', 'Перенесено'),
        node('span', 'itc-ghost-link', `Актуальное время: ${formatDate(nd, { weekday: 'short', day: 'numeric', month: 'long' })}, ${event.moved.start_time}`));
      button.addEventListener('click', () => { $('#event-dialog').close(); jumpTo(event.moved); });
      list.append(button);
      continue;
    }
    if (event.status !== 'scheduled') button.append(node('span', 'event-badge', statusNames[event.status]));
    button.addEventListener('click', () => { $('#event-dialog').close(); details(event); });
    list.append(button);
  }
  target.append(list);
  $('#event-dialog').showModal();
}

function groupCard(group) {
  const count = group.events.length;
  const forms = { one: 'занятие', few: 'занятия', many: 'занятий', other: 'занятия' };
  const label = `${count} ${forms[new Intl.PluralRules('ru').select(count)]}`;
  const button = node('button', 'calendar-event parallel-group');
  button.type = 'button';
  button.setAttribute('aria-label', `${label} в этот период. Открыть список.`);
  button.append(node('strong', 'parallel-group-count', label));
  const preview = node('span', 'parallel-group-preview');
  for (const event of group.events.slice(0, 3)) {
    const line = node('span', 'parallel-group-line');
    const dot = node('span', 'parallel-group-dot');
    dot.style.backgroundColor = clubColor(event.club_id, event.category_color, event.category_name);
    line.append(dot, node('span', '', event.ghost ? `${event.club_name} · перенесено` : event.club_name));
    preview.append(line);
  }
  button.append(preview);
  button.addEventListener('click', () => openEventGroup(group.events));
  return button;
}

function emptyState(title, description, action) {
  const card = node('div', 'schedule-state');
  card.append(node('h3', '', title), node('p', '', description));
  if (action) {
    const button = node('button', '', action.label);
    button.type = 'button';
    button.addEventListener('click', action.run);
    card.append(button);
  }
  return card;
}

// Заглушки загрузки: та же сетка/список, вместо карточек — мерцающие плашки (по две на день: 10:00 и 15:00)
function skeletonCard() {
  const card = node('div', 'calendar-event skel');
  card.append(node('span', 'skel-bar skel-time'), node('span', 'skel-bar skel-name'), node('span', 'skel-bar skel-room'));
  return card;
}

function renderSkeleton(days) {
  const slots = [['10:00', '11:30'], ['15:00', '16:30']];
  const events = days.flatMap(day => slots.map(([start_time, end_time], i) => ({ event_id: `skel-${day}-${i}`, date: dateKey(addDays(state.week, day)), start_time, end_time, club_id: 0, club_name: '' })));
  if (mobile.matches || state.view === 'list') renderList(events, days, { skeleton: true });
  else renderGrid(events, days, { skeleton: true });
  const shell = content.lastElementChild;
  shell.classList.add('schedule-skeleton', 'is-loading');
  shell.setAttribute('aria-hidden', 'true');
  shell.removeAttribute('role');
  shell.removeAttribute('tabindex');
  shell.removeAttribute('aria-label');
}

// Снимаем скелетон с потока и кладём поверх: под ним рендерится настоящее расписание, затем каскад (skeleton-cascade.js)
function detachSkeleton() {
  const shell = content.querySelector(':scope > .schedule-skeleton');
  if (!shell) return null;
  const box = content.getBoundingClientRect(), rect = shell.getBoundingClientRect();
  const scrollLeft = shell.scrollLeft;
  shell.classList.add('is-leaving');
  Object.assign(shell.style, { top: `${rect.top - box.top}px`, left: `${rect.left - box.left}px`, width: `${rect.width}px`, height: `${rect.height}px` });
  shell.remove();
  return { shell, scrollLeft };
}

function startCascade(leaving) {
  content.append(leaving.shell);
  leaving.shell.scrollLeft = leaving.scrollLeft;
  const items = [...content.querySelectorAll('.calendar-event, .track-empty, .day-empty, :scope > .schedule-state')].filter(el => !leaving.shell.contains(el));
  const cascade = runCascade([...leaving.shell.querySelectorAll('.skel')], items, { reduced: prefersReducedMotion() });
  const done = () => { leaving.shell.remove(); if (activeCascade === handle) activeCascade = null; };
  const handle = { cancel() { cascade.cancel(); done(); } };
  cascade.finished.then(done);
  activeCascade = handle;
}

function renderList(events, days, { skeleton = false } = {}) {
  const list = node('div', 'schedule-list');
  for (const day of days) {
    const date = addDays(state.week, day);
    const group = node('div', 'list-day');
    const heading = node('h3', '', `${DAY_NAMES[day]}, ${formatDate(date)}`);
    group.append(heading);
    const daily = events.filter(event => event.date === dateKey(date)).sort((a, b) => a.start_time.localeCompare(b.start_time) || a.club_name.localeCompare(b.club_name, 'ru'));
    if (daily.length === 0 && !skeleton) group.append(node('p', 'day-empty', 'Занятий нет'));
    for (const event of daily) group.append(skeleton ? skeletonCard() : eventCard(event));
    list.append(group);
  }
  content.append(list);
}

function renderGrid(events, days, { skeleton = false } = {}) {
  const dayWidths = days.map(() => 155);
  const earliest = Math.floor(Math.min(...events.map(event => minutes(event.start_time))) / 60);
  const latest = Math.ceil(Math.max(...events.map(event => minutes(event.end_time))) / 60);
  const start = Math.max(0, earliest);
  const end = Math.min(24, Math.max(latest, start + 4));
  const hourHeight = 80;
  const height = (end - start) * hourHeight;
  const grid = node('div', 'week-grid');
  grid.setAttribute('role', 'region');
  grid.setAttribute('aria-label', 'Недельная сетка расписания. Прокрутите горизонтально, чтобы увидеть все дни.');
  grid.tabIndex = 0;
  grid.style.setProperty('--grid-columns', `66px ${dayWidths.map(width => `minmax(${width}px, 1fr)`).join(' ')}`);
  grid.style.setProperty('--grid-width', `${66 + dayWidths.reduce((sum, width) => sum + width, 0)}px`);
  grid.style.setProperty('--hour-height', `${hourHeight}px`);
  const headings = node('div', 'grid-headings');
  headings.append(node('span', 'time-zone', 'МСК'));
  for (const day of days) {
    const date = addDays(state.week, day);
    const heading = node('div', 'grid-day-heading');
    heading.classList.toggle('is-today', dateKey(date) === dateKey(currentStudyDay()));
    if (day === state.day && new URLSearchParams(location.search).has('day')) heading.setAttribute('aria-current', 'date');
    heading.append(node('span', '', DAY_NAMES[day]), node('strong', '', String(date.getDate())));
    headings.append(heading);
  }
  const tracks = node('div', 'grid-tracks');
  const scale = node('div', 'time-scale');
  scale.style.height = `${height}px`;
  for (let hour = start; hour <= end; hour++) {
    const tick = node('span', '', `${String(hour).padStart(2, '0')}:00`);
    tick.style.top = `${(hour - start) * hourHeight}px`;
    scale.append(tick);
  }
  tracks.append(scale);
  for (const day of days) {
    const date = addDays(state.week, day);
    const track = node('div', 'day-track');
    track.setAttribute('role', 'group');
    track.setAttribute('aria-label', `${DAY_NAMES[day]}, ${formatDate(date)}`);
    track.style.height = `${height}px`;
    track.classList.toggle('is-today', dateKey(date) === dateKey(currentStudyDay()));
    const daily = events.filter(event => event.date === dateKey(date));
    if (daily.length === 0 && !skeleton) track.append(node('span', 'track-empty', 'Нет занятий'));
    for (const group of eventGroups(daily)) {
      const duration = (group.end - group.start) / 60 * hourHeight;
      const card = skeleton ? skeletonCard() : group.events.length === 1 ? eventCard(group.events[0], duration < 110) : groupCard(group);
      card.style.top = `${(group.start / 60 - start) * hourHeight + 2}px`;
      card.style.height = `${Math.max(4, duration - 4)}px`;
      card.style.left = '3px';
      card.style.width = 'calc(100% - 6px)';
      track.append(card);
    }
    tracks.append(track);
  }
  grid.append(headings, tracks);
  content.append(grid);
}

function render(direction = 0) {
  ui.updateControls();
  activeCascade?.cancel();
  const leaving = state.phase !== 'loading' ? detachSkeleton() : null;
  content.replaceChildren();
  content.setAttribute('aria-busy', String(state.phase === 'loading'));
  if (state.phase === 'loading') {
    $('#result-status').textContent = 'Загружаем расписание…';
    renderSkeleton(mobile.matches ? [state.day] : visibleDays());
    return;
  }
  try { renderContent(); } finally { if (leaving) startCascade(leaving); }
  const animation = direction && mobile.matches && !prefersReducedMotion() && content.firstElementChild?.animate?.(
    [{ opacity: .45, transform: 'translateX(' + direction * 14 + 'px)' }, { opacity: 1, transform: 'none' }],
    { duration: 190, easing: 'ease-out' });
  ui.focusPending(content, animation);

}

function renderContent() {
  if (state.phase === 'error') {
    $('#result-status').textContent = 'Расписание не загружено';
    content.append(emptyState('Не получилось загрузить расписание', state.error, { label: 'Повторить попытку', run: () => ui.load({ refresh: true }) }));
    return;
  }
  const days = mobile.matches ? [state.day] : visibleDays();
  const inDays = list => list.filter(event => days.some(day => event.date === dateKey(addDays(state.week, day))));
  const real = inDays(state.events);
  const events = real.concat(inDays(ghostEvents(state.events)));
  const active = real.filter(event => event.status !== 'cancelled').length;
  const cancelled = real.length - active;
  $('#result-status').textContent = `${mobile.matches ? DAY_NAMES[state.day] : 'За выбранные дни'}: ${active} · отменено: ${cancelled}${ui.hasFilters() ? ' · фильтры включены' : ''}`;
  if (events.length === 0) {
    const label = mobile.matches ? ` · ${DAY_NAMES[state.day]}, ${formatDate(addDays(state.week, state.day))}` : '';
    if (ui.inMyMode() && !ui.hasFilters()) {
      content.append(emptyState('В «Моих кружках» занятий нет' + label, 'Выбери другой день или выключи «Мои кружки».'));
      return;
    }
    const title = (ui.hasFilters() ? 'Ничего не нашлось' : 'Занятий пока нет') + label;
    const help = ui.hasFilters()
      ? (mobile.matches ? 'Выбери другой день или поменяй фильтры.' : 'Попробуй другое сочетание фильтров или сбрось их.')
      : 'Выбери другой день или неделю. Здесь появятся занятия, добавленные в расписание.';
    content.append(emptyState(title, help, ui.hasFilters() ? { label: 'Сбросить фильтры', run: () => $('#reset-filters').click() } : undefined));
  } else if (mobile.matches || state.view === 'list') renderList(events, days);
  else renderGrid(events, days);
}

const ui = mountScheduleUi({
  state, render, dayView: () => mobile.matches,
  onRooms(data) { rooms.clear(); for (const room of data) rooms.set(room.id, room); },
});
for (const view of ['grid', 'list']) {
  $(`#view-${view}`).addEventListener('click', () => { state.view = view; render(); });
}
mobile.addEventListener('change', () => render());
ui.loadReferences();
ui.load();
