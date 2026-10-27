import { getSchedule, getCategories, getLeaders, getRooms } from './api.js';
import { DAY_NAMES, DAY_SHORT, parseDate, dateKey, addDays, monday, moscowToday, formatDate, minutes, eventGroups } from './schedule-dates.js';
import { clubColor } from './event-colors.js';
import { icon } from './icons.js';
import { eventRoom } from './public-display.js';
import { latestRequest } from './latest-request.js';

const $ = selector => document.querySelector(selector);
const content = $('#content');
const mobile = window.matchMedia('(max-width: 999px)');
const today = moscowToday();
// Те же границы, что у API (понедельники недель): иначе сервер ответит 422
const WEEK_MIN = '2000-01-03';
const WEEK_MAX = '2100-12-27';
const state = { week: monday(today), day: Math.min((today.getDay() + 6) % 7, 5), view: 'grid', filtersOpen: false, events: [], phase: 'loading', error: '' };
const fields = { search: $('#search'), category_id: $('#category'), weekday: $('#weekday'), leader_id: $('#leader'), room_id: $('#room') };
const statusNames = { scheduled: 'По расписанию', moved: 'Перенос', cancelled: 'Отменено' };
const scheduleRequest = latestRequest();
let searchTimer;
let referencesId = 0;
const rooms = new Map();

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function filters() {
  return Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value.trim()]));
}

function hasFilters() { return Object.values(filters()).some(Boolean); }

function visibleDays() { return fields.weekday.value ? [Number(fields.weekday.value) - 1] : [0, 1, 2, 3, 4, 5]; }

function rangeLabel() {
  const end = addDays(state.week, 5);
  const startLabel = state.week.getMonth() === end.getMonth() ? String(state.week.getDate()) : formatDate(state.week);
  return `${startLabel} — ${formatDate(end)}`;
}

function updateControls() {
  $('#filter-options').hidden = mobile.matches && !state.filtersOpen;
  $('#toggle-filters').setAttribute('aria-expanded', String(state.filtersOpen));
  const filterCount = Object.entries(filters()).filter(([key, value]) => key !== 'search' && value).length;
  $('#toggle-filters span').textContent = `${state.filtersOpen ? 'Скрыть' : 'Фильтры'}${filterCount ? ` · ${filterCount}` : ''}`;
  $('#week-label').textContent = rangeLabel();
  const end = addDays(state.week, 5);
  $('#week-year').textContent = state.week.getFullYear() === end.getFullYear() ? String(state.week.getFullYear()) : `${state.week.getFullYear()} / ${end.getFullYear()}`;
  $('#week-date').value = dateKey(addDays(state.week, state.day));
  $('#prev-week').disabled = dateKey(addDays(state.week, -7)) < WEEK_MIN;
  $('#next-week').disabled = dateKey(addDays(state.week, 7)) > WEEK_MAX;
  $('#prev-day').disabled = state.day === 0 && $('#prev-week').disabled;
  $('#next-day').disabled = state.day === 5 && $('#next-week').disabled;
  $('#selected-day-label').textContent = `${DAY_NAMES[state.day]}, ${formatDate(addDays(state.week, state.day))}`;
  $('#view-grid').setAttribute('aria-pressed', String(state.view === 'grid'));
  $('#view-list').setAttribute('aria-pressed', String(state.view === 'list'));
  // Сохраняем кнопки в DOM: фокус клавиатуры не теряется при выборе дня.
  for (const [index, button] of [...$('#day-buttons').children].entries()) {
    const date = addDays(state.week, index);
    button.replaceChildren(node('span', '', DAY_SHORT[index]), node('strong', '', String(date.getDate())));
    button.setAttribute('aria-label', `${DAY_NAMES[index]}, ${formatDate(date)}`);
    button.setAttribute('aria-pressed', String(state.day === index));
    button.classList.toggle('is-today', dateKey(date) === dateKey(today));
  }
}

function safeEvents(data) {
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  if (!Array.isArray(data) || data.some(event => !event || typeof event.event_id !== 'string'
    || !Number.isInteger(event.club_id) || event.club_id <= 0 || !parseDate(event.date)
    || !timePattern.test(event.start_time) || !timePattern.test(event.end_time)
    || minutes(event.start_time) >= minutes(event.end_time)
    || !['club_name', 'leader_name', 'room_name', 'category_name'].every(key => typeof event[key] === 'string')
    || !Object.hasOwn(statusNames, event.status))) {
    throw new Error('Сервер вернул расписание в неожиданном формате. Попробуй обновить данные.');
  }
  const first = dateKey(state.week);
  const last = dateKey(addDays(state.week, 5));
  return data.filter(event => event.date >= first && event.date <= last);
}

async function loadSchedule() {
  clearTimeout(searchTimer);
  const request = scheduleRequest.begin();
  state.phase = 'loading';
  state.events = [];
  render();
  try {
    const data = await getSchedule(dateKey(state.week), filters(), { signal: request.signal });
    if (!request.isCurrent()) return;
    state.events = safeEvents(data);
    state.phase = 'ready';
  } catch (error) {
    if (!request.isCurrent() || error.name === 'AbortError') return;
    state.phase = 'error';
    state.error = error.message;
  }
  render();
}

function scheduleSearch() {
  // Отменяем старый запрос сразу, ещё до задержки поиска.
  scheduleRequest.cancel();
  clearTimeout(searchTimer);
  state.phase = 'loading';
  state.events = [];
  render();
  searchTimer = setTimeout(loadSchedule, 250);
}

async function loadReferences() {
  const id = ++referencesId;
  const definitions = [
    ['category_id', getCategories, 'направлений'],
    ['leader_id', getLeaders, 'руководителей'],
    ['room_id', getRooms, 'аудиторий'],
  ];
  $('#retry-references').disabled = true;
  const results = await Promise.allSettled(definitions.map(([, get]) => get()));
  if (id !== referencesId) return;
  const failed = [];
  results.forEach((result, index) => {
    const [key, , title] = definitions[index];
    const select = fields[key];
    const data = result.status === 'fulfilled' ? result.value : null;
    if (!Array.isArray(data) || data.some(item => !Number.isInteger(item.id) || item.id <= 0 || typeof item.name !== 'string')) {
      failed.push(title);
      return;
    }
    if (key === 'room_id') { rooms.clear(); for (const room of data) rooms.set(room.id, room); }
    const selected = select.value;
    select.replaceChildren(select.options[0]);
    for (const item of data) {
      const option = node('option', '', key === 'room_id' && item.building ? `${item.name} · ${item.building}` : item.name);
      option.value = String(item.id);
      select.append(option);
    }
    select.value = selected;
    select.disabled = false;
  });
  $('#reference-error').hidden = failed.length === 0;
  $('#reference-error span').textContent = `Не удалось загрузить список ${failed.join(', ')}. Доступные фильтры продолжают работать.`;
  $('#retry-references').disabled = false;
  if (state.phase === 'ready') render();
}

function showWeek(date) {
  const week = monday(date);
  if (dateKey(week) < WEEK_MIN || dateKey(week) > WEEK_MAX) return;
  state.week = week;
  loadSchedule();
}

function selectDay(day) {
  state.day = day;
  if (fields.weekday.value) {
    fields.weekday.value = String(day + 1);
    loadSchedule();
  } else render();
}

function shiftDay(delta) {
  const next = state.day + delta;
  state.day = (next + 6) % 6;
  if (fields.weekday.value) fields.weekday.value = String(state.day + 1);
  if (next < 0 || next > 5) showWeek(addDays(state.week, delta * 7));
  else if (fields.weekday.value) loadSchedule();
  else render();
}

function resetFilters() {
  for (const input of Object.values(fields)) input.value = '';
  loadSchedule();
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
  target.append(info);
  if (event.comment) target.append(node('p', 'event-comment', event.comment));
  const link = node('a', 'club-link', 'О кружке');
  link.append(icon('arrow'));
  link.href = `/club.html?id=${event.club_id}`;
  target.append(link);
  $('#event-dialog').showModal();
}

function eventCard(event, compact = false) {
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
    line.append(dot, node('span', '', event.club_name));
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

function renderList(events, days) {
  const list = node('div', 'schedule-list');
  for (const day of days) {
    const date = addDays(state.week, day);
    const group = node('div', 'list-day');
    const heading = node('h3', '', `${DAY_NAMES[day]}, ${formatDate(date)}`);
    group.append(heading);
    const daily = events.filter(event => event.date === dateKey(date)).sort((a, b) => a.start_time.localeCompare(b.start_time) || a.club_name.localeCompare(b.club_name, 'ru'));
    if (daily.length === 0) group.append(node('p', 'day-empty', 'Занятий нет'));
    for (const event of daily) group.append(eventCard(event));
    list.append(group);
  }
  content.append(list);
}

function renderGrid(events, days) {
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
    heading.classList.toggle('is-today', dateKey(date) === dateKey(today));
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
    track.classList.toggle('is-today', dateKey(date) === dateKey(today));
    const daily = events.filter(event => event.date === dateKey(date));
    if (daily.length === 0) track.append(node('span', 'track-empty', 'Нет занятий'));
    for (const group of eventGroups(daily)) {
      const duration = (group.end - group.start) / 60 * hourHeight;
      const card = group.events.length === 1 ? eventCard(group.events[0], duration < 110) : groupCard(group);
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

function render() {
  updateControls();
  content.replaceChildren();
  content.setAttribute('aria-busy', String(state.phase === 'loading'));
  if (state.phase === 'loading') {
    $('#result-status').textContent = 'Загружаем расписание…';
    content.append(emptyState('Загружаем занятия', 'Получаем актуальное расписание с сервера.'));
    content.firstElementChild.classList.add('is-loading');
    return;
  }
  if (state.phase === 'error') {
    $('#result-status').textContent = 'Расписание не загружено';
    content.append(emptyState('Не получилось загрузить расписание', state.error, { label: 'Повторить попытку', run: loadSchedule }));
    return;
  }
  const days = mobile.matches ? [state.day] : visibleDays();
  const events = state.events.filter(event => days.some(day => event.date === dateKey(addDays(state.week, day))));
  const active = events.filter(event => event.status !== 'cancelled').length;
  const cancelled = events.length - active;
  $('#result-status').textContent = `${mobile.matches ? 'За день' : 'За выбранные дни'}: ${active} · отменено: ${cancelled}${hasFilters() ? ' · фильтры включены' : ''}`;
  if (events.length === 0) {
    content.append(emptyState(hasFilters() ? 'Ничего не нашлось' : 'Занятий пока нет', hasFilters() ? 'Попробуй другое сочетание фильтров или сбрось их.' : 'Выбери другой день или неделю. Здесь появятся занятия, добавленные в расписание.', hasFilters() ? { label: 'Сбросить фильтры', run: resetFilters } : undefined));
  } else if (mobile.matches || state.view === 'list') renderList(events, days);
  else renderGrid(events, days);
}

for (let day = 0; day < 6; day++) {
  const button = node('button');
  button.type = 'button';
  button.addEventListener('click', () => selectDay(day));
  $('#day-buttons').append(button);
}
$('#prev-week').addEventListener('click', () => showWeek(addDays(state.week, -7)));
$('#next-week').addEventListener('click', () => showWeek(addDays(state.week, 7)));
$('#prev-day').addEventListener('click', () => shiftDay(-1));
$('#next-day').addEventListener('click', () => shiftDay(1));
$('#today').addEventListener('click', () => {
  const current = moscowToday();
  state.day = Math.min((current.getDay() + 6) % 7, 5);
  if (fields.weekday.value) fields.weekday.value = String(state.day + 1);
  showWeek(current);
});
$('#week-date').addEventListener('change', event => {
  const date = parseDate(event.target.value);
  if (!date || !event.target.validity.valid) { updateControls(); return; }
  state.day = Math.min((date.getDay() + 6) % 7, 5);
  if (fields.weekday.value) fields.weekday.value = String(state.day + 1);
  showWeek(date);
});
for (const view of ['grid', 'list']) $(`#view-${view}`).addEventListener('click', () => { state.view = view; render(); });
$('#schedule-filters').addEventListener('submit', event => { event.preventDefault(); loadSchedule(); });
fields.search.addEventListener('input', scheduleSearch);
for (const [key, field] of Object.entries(fields)) {
  if (key === 'search') continue;
  field.addEventListener('change', () => {
    if (key === 'weekday' && field.value) state.day = Number(field.value) - 1;
    loadSchedule();
  });
}
$('#reset-filters').addEventListener('click', resetFilters);
$('#toggle-filters').addEventListener('click', () => { state.filtersOpen = !state.filtersOpen; updateControls(); });
$('#retry-references').addEventListener('click', loadReferences);
$('#close-event').addEventListener('click', () => $('#event-dialog').close());
mobile.addEventListener('change', render);
for (const key of ['category_id', 'leader_id', 'room_id']) fields[key].disabled = true;
loadReferences();
loadSchedule();
