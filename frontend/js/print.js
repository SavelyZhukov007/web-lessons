import { getSchedule } from './api.js';
import { DAY_NAMES, addDays, dateKey, formatDate, moscowToday } from './schedule-dates.js';
import { WEEK_MAX, WEEK_MIN, buildPrintDays, dateHuman, weekFromQuery, weekRange } from './print-logic.js';

const $ = selector => document.querySelector(selector);

const weekNode = $('.print-schedule-week');
const weekCaptionNode = $('.schedule-week-caption');
const nextButton = $('#next-button');
const prevButton = $('#prev-button');
const printButton = $('#print-button');
const headerBrandNode = $('.print-schedule-header-brand');

let requestController = null;

const state = {
  weekStart: weekFromQuery(location.search, moscowToday()),
  days: [],
  phase: 'loading',
  error: '',
};

async function loadSchedule() {
  requestController?.abort();
  const controller = new AbortController();
  requestController = controller;
  state.phase = state.phase === 'ready' ? 'updating' : 'loading';
  state.error = '';
  render();
  try {
    const data = await getSchedule(dateKey(state.weekStart), {}, { signal: controller.signal });
    if (requestController !== controller) return; // ответ устаревшего запроса
    state.days = buildPrintDays(data, state.weekStart);
    state.phase = 'ready';
  } catch (error) {
    if (requestController !== controller || error.name === 'AbortError') return;
    state.phase = 'error';
    state.error = error.message || 'Не получилось загрузить расписание.';
  }
  requestController = null;
  render();
}

function node(tag, className, text = '') {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text) item.textContent = text;
  return item;
}

function render() {
  updateToolbar();
  if (state.phase === 'updating') { renderBrand(true); return; }
  renderBrand(false);
  weekNode.replaceChildren();
  if (state.phase === 'loading') weekNode.append(node('h1', 'print-schedule-loading', 'Загрузка данных...'));
  else if (state.phase === 'error') weekNode.append(node('h1', 'print-schedule-error', state.error));
  else assembleSchedule();
}

function createBrand() {
  const brand = node('a', 'campus-brand');
  brand.href = '/';
  brand.setAttribute('aria-label', 'KipClub — главная');
  const mark = node('span', 'brand-mark');
  mark.setAttribute('aria-hidden', 'true');
  brand.append(mark, node('span', '', 'KipClub'));
  return brand;
}

function renderBrand(loading) {
  headerBrandNode.replaceChildren(createBrand());
  if (!loading) return;
  const wrapper = node('div', 'loading-circle-wrapper');
  wrapper.append(node('div', 'loading-circle'));
  headerBrandNode.append(wrapper);
}

function assembleSchedule() {
  state.days.forEach((day, i) => {
    const daySchedule = node('div', 'print-schedule-day');
    daySchedule.append(node('h3', '', `${DAY_NAMES[i]}, ${formatDate(day.date)}`));
    if (!day.rows.length) daySchedule.append(node('p', 'print-schedule-empty', 'Занятий нет'));
    for (const row of day.rows) daySchedule.append(createRow(row));
    weekNode.append(daySchedule);
  });
}

function createRow(row) {
  const eventNode = node('div', 'print-schedule-lesson');
  const timeNode = node('span', 'ps-lesson-time');
  const leftColumn = node('div', 'print-schedule-lesson-left');
  const midColumn = node('div', 'print-schedule-lesson-mid');
  const rightColumn = node('div', 'print-schedule-lesson-right');
  timeNode.append(node('span', 'ps-lesson-time-start', row.slotStart), node('span', 'ps-lesson-time-end', row.slotEnd));
  const nameNode = node('strong', 'ps-lesson-name', row.club);
  const roomNode = node('span', 'ps-lesson-room', row.rooms);
  const leaderNode = node('span', 'ps-lesson-leader', row.leaders);
  if (row.status === 'cancelled' || row.ghost) {
    for (const item of [nameNode, roomNode, leaderNode, timeNode]) item.classList.add('crossed-out');
  }
  leftColumn.append(timeNode);
  if (row.note) leftColumn.append(node('span', 'ps-lesson-status', row.note));
  midColumn.append(nameNode, roomNode);
  rightColumn.append(leaderNode);
  eventNode.append(leftColumn, midColumn, rightColumn);
  return eventNode;
}

function updateToolbar() {
  const { start, end } = weekRange(state.weekStart);
  weekCaptionNode.textContent = `${dateHuman(start)} — ${dateHuman(end)} (Пн–Сб)`;
}

function loadWeek(date) {
  const key = dateKey(date);
  if (key < WEEK_MIN || key > WEEK_MAX) return;
  state.weekStart = date;
  const url = new URL(location.href);
  url.searchParams.set('week', key);
  history.replaceState(null, '', url);
  loadSchedule();
}

prevButton.addEventListener('click', () => loadWeek(addDays(state.weekStart, -7)));
nextButton.addEventListener('click', () => loadWeek(addDays(state.weekStart, 7)));
printButton.addEventListener('click', () => window.print());

loadSchedule();
