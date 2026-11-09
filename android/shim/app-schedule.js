// APK uses the same schedule controls as the web. It renders parallel
// sessions as a slot and keeps the native splash and quick admin actions.
import { DAY_NAMES, parseDate, dateKey, addDays, formatDate, minutes, scheduleLocation, movedFromSlot } from './schedule-dates.js';
import { currentStudyDay, mountScheduleUi } from './schedule-ui.js';
import { eventShareControls } from './schedule-share.js';
import { openScheduleFilters } from './app-schedule-filters.js';
import { icon } from './icons.js';
import { clubColor } from './event-colors.js';

const $ = s => document.querySelector(s);
const statusNames = { scheduled: 'По расписанию', moved: 'Перенос', cancelled: 'Отменено' };
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const splash = window.ItcSplash || { progress() {}, done() {} };

const state = { ...scheduleLocation(location.search, currentStudyDay()), events: [], phase: 'loading', error: '' };
window.ItcEvent = id => state.events.find(event => event.event_id === id);
const cards = new Map();
let firstContent = false;

function node(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

const content = $('#content');
const status = $('#result-status');
document.body.classList.add('app-schedule');
content.classList.add('app-content');

function sig(e) { return [e.status, e.start_time, e.end_time, e.club_name, e.room_name, e.leader_name, JSON.stringify(e.room_names), JSON.stringify(e.leader_names), e.category_color, e.date, e.original_date, e.comment].join('\u0001'); }
function anyCard(x) { return x.ghost ? ghostCard(x.e) : card(x); }
function ghostCard(e) {
  const nd = parseDate(e.date), box = node('div', 'calendar-event itc-ghost');
  box.setAttribute('role', 'group'); box.setAttribute('aria-label', `${e.club_name}: перенесено на ${formatDate(nd)}, ${e.start_time}`);
  const time = node('span', 'event-time itc-ghost-time');
  if (e.original_start_time) time.append(node('s', '', `${e.original_start_time}–${e.original_end_time}`)); else time.append(node('s', '', 'обычное время'));
  const go = node('button', 'itc-ghost-link', `Актуальное время: ${formatDate(nd, { weekday: 'short', day: 'numeric', month: 'long' })}, ${e.start_time}`);
  go.type = 'button';
  go.addEventListener('click', () => { window.ItcHaptics?.tap(); ui.jumpTo(e); });
  box.append(time, node('strong', 'event-name', e.club_name), node('span', 'event-badge', 'Перенесено'), go);
  return box;
}
function card(e) {
  const s = sig(e), c = cards.get(e.event_id);
  if (c && c.sig === s) { c.event = e; return c.node; }
  const b = node('button', `calendar-event ${e.status}${e.status !== 'scheduled' ? ' has-status' : ''}`);
  b.type = 'button'; b.dataset.eventId = e.event_id;
  b.style.setProperty('--event-color', clubColor(e.club_id, e.category_color, e.category_name));
  b.setAttribute('aria-label', `${e.club_name}. ${formatDate(parseDate(e.date))}, ${e.start_time}–${e.end_time}. ${(e.room_names || [e.room_name]).join(', ')}. ${(e.leader_names || [e.leader_name]).join(', ')}. ${statusNames[e.status]}. Открыть подробности.`);
  const time = node('span', 'event-time');
  time.append(node('span', 'event-start', e.start_time), node('span', 'time-divider', '–'), node('span', 'event-end', e.end_time));
  b.append(time, node('strong', 'event-name', e.club_name), node('span', 'event-room', (e.room_names || [e.room_name]).join(', ')), node('span', 'event-leader', (e.leader_names || [e.leader_name]).join(', ')));
  if (e.status !== 'scheduled') b.append(node('span', 'event-badge', statusNames[e.status]));
  b.append(icon('right', 'event-affordance'));
  const rec = { sig: s, node: b, event: e };
  b.addEventListener('click', () => details(rec.event));
  cards.set(e.event_id, rec);
  return b;
}
function emptyState(title, text, action) {
  const box = node('div', 'schedule-state'); box.append(node('h3', '', title), node('p', '', text));
  if (action) { const b = node('button', '', action.label); b.type = 'button'; b.addEventListener('click', action.run); box.append(b); }
  return box;
}
function skeleton() {
  const box = node('div', 'app-skeleton is-loading'); box.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < 3; i++) box.append(node('div', 'app-skel-card'));
  return box;
}
// Занятия дня: одинаковое начало → «слот» параллельных занятий (аудитория и руководитель — бейджами)
function dayChildren() {
  if (state.phase === 'loading') return [skeleton()];
  if (state.phase === 'error') return [emptyState('Не получилось загрузить расписание', state.error, { label: 'Повторить попытку', run: () => ui.load({ refresh: true }) })];
  const key = dateKey(addDays(state.week, state.day));
  // t102: перенесённое занятие оставляет в старом слоте приглушённую карточку «Перенесено» → «Актуальное время»
  const ghosts = state.events.filter(e => e.original_date === key && movedFromSlot(e))
    .map(e => ({ ghost: true, e, start_time: e.original_start_time || '', end_time: e.original_end_time || '', club_name: e.club_name }));
  const daily = state.events.filter(e => e.date === key).concat(ghosts)
    .sort((a, b) => a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time) || a.club_name.localeCompare(b.club_name, 'ru'));
  if (!daily.length) {
    if (ui.hasFilters()) return [emptyState(`Ничего не нашлось · ${DAY_NAMES[state.day]}, ${formatDate(parseDate(key))}`, 'Выбери другой день или поменяй фильтры.', { label: 'Сбросить фильтры', run: () => $('#reset-filters').click() })];
    if (window.ItcFeatures?.isMyMode()) return [emptyState('В «Моих кружках» занятий нет', 'В этот день у отмеченных кружков ничего нет. Смахни влево — следующий день, или выключи «Мои кружки».')];
    return [emptyState('Занятий нет', 'В этот день кружков нет. Смахни влево или вправо, чтобы посмотреть соседние дни.')];
  }
  const out = [];
  for (let i = 0; i < daily.length;) {
    let j = i + 1;
    while (j < daily.length && daily[j].start_time === daily[i].start_time) j++;
    if (j - i === 1) out.push(anyCard(daily[i]));
    else {
      const slot = node('section', 'app-slot');
      const ends = new Set(daily.slice(i, j).map(e => e.end_time));
      slot.setAttribute('aria-label', `Параллельно в ${daily[i].start_time}: ${j - i} занятия`);
      const head = node('header', 'app-slot-head');
      head.append(node('span', 'app-slot-time', ends.size === 1 ? `${daily[i].start_time}–${daily[i].end_time}` : `с ${daily[i].start_time}`), node('span', 'app-slot-count', `параллельно · ${j - i}`));
      const list = node('div', 'app-slot-cards');
      list.append(...daily.slice(i, j).map(anyCard));
      slot.append(head, list); out.push(slot);
    }
    i = j;
  }
  return out;
}
function setStatus() {
  if (state.phase === 'loading') { status.textContent = 'Загружаем расписание…'; return; }
  if (state.phase === 'error') { status.textContent = 'Расписание не загружено'; return; }
  const key = dateKey(addDays(state.week, state.day));
  const d = state.events.filter(e => e.date === key);
  const c = d.filter(e => e.status === 'cancelled').length;
  status.textContent = `${DAY_NAMES[state.day]}: занятий ${d.length - c}${c ? `, отменено ${c}` : ''}`;
}
let pane = null, animating = null;
function render(dir = 0) {
  ui.updateControls(); setStatus();
  content.setAttribute('aria-busy', String(state.phase === 'loading'));
  const kids = dayChildren();
  if (!pane || !pane.isConnected) { pane = node('div', 'app-pane'); content.replaceChildren(pane); }
  let transition;
  if (dir && !reduced.matches && pane.childElementCount) transition = slide(kids, dir);
  else {
    // по ключу: те же узлы карточек переиспользуются, меняется только то, что изменилось
    const same = kids.length === pane.children.length && kids.every((k, i) => k === pane.children[i]);
    if (!same) pane.replaceChildren(...kids);
  }
  if (state.phase === 'ready' || state.phase === 'error') contentReady();
  ui.focusPending(pane, transition);
}
function slide(kids, dir) {
  if (animating) animating.finish();
  const old = pane;
  const previousHeight = content.offsetHeight;
  const next = node('div', 'app-pane'); next.append(...kids);
  content.style.minHeight = `${previousHeight}px`;
  old.inert = true;
  old.classList.add('app-pane-out'); content.append(next); pane = next;
  const opts = { duration: 240, easing: 'cubic-bezier(.2,.8,.2,1)' };
  const a1 = old.animate([{ transform: 'none' }, { transform: `translateX(${-dir * 18}px)`, opacity: 0 }], opts);
  const a2 = next.animate([{ transform: `translateX(${dir * 24}px)`, opacity: 0.4 }, { transform: 'none', opacity: 1 }], opts);
  animating = a2;
  const end = () => {
    old.remove();
    if (animating === a2) { animating = null; content.style.minHeight = ''; }
  };
  a2.finished.then(end, end); a1.finished.catch(() => {});
  return a2;
}
function contentReady() {
  if (firstContent) return; firstContent = true;
  window.ItcPerf = Object.assign(window.ItcPerf || {}, { firstContent: performance.now() });
  splash.progress(1); splash.done();
}

// ---------- подробности ----------
function details(e) {
  const t = $('#event-details'); t.replaceChildren();
  t.append(node('p', `event-badge ${e.status}`, statusNames[e.status]));
  const title = node('h2', '', e.club_name); title.id = 'event-title'; t.append(title);
  const dl = node('dl', 'event-facts');
  const facts = [['Когда', `${formatDate(parseDate(e.date), { year: 'numeric' })}, ${e.start_time}–${e.end_time}`], ['Аудитория', (e.room_names || [e.room_name]).join(', ')], ['Руководитель', (e.leader_names || [e.leader_name]).join(', ')], ['Направление', e.category_name]];
  if (e.status === 'moved' && parseDate(e.original_date)) facts.push(['Исходная дата', formatDate(parseDate(e.original_date), { year: 'numeric' })]);
  const same = state.events.filter(x => x.event_id !== e.event_id && x.date === e.date && x.status !== 'cancelled' && minutes(x.start_time) < minutes(e.end_time) && minutes(e.start_time) < minutes(x.end_time));
  if (same.length) facts.push(['Параллельно', same.map(x => `${x.club_name} (${x.room_name})`).join(', ')]);
  for (const [k, v] of facts) dl.append(node('dt', '', k), node('dd', '', v));
  t.append(dl);
  if (e.comment) t.append(node('p', 'event-comment', e.comment));
  const a = node('a', 'club-link', 'О кружке'); a.append(icon('arrow')); a.href = `/club.html?id=${e.club_id}`; t.append(eventShareControls(e, a));
  const dlg = $('#event-dialog'); if (!dlg.open) dlg.showModal();
}

const ui = mountScheduleUi({
  state, render, dayView: () => true, openFilters: openScheduleFilters,
  onPhase: phase => splash.progress(phase === 'loading' ? 0.6 : 0.9),
});
window.ItcSchedule = { shiftDay: ui.shiftDay, shiftWeek: ui.shiftWeek, goto: value => ui.goto(parseDate(value)), state };
splash.progress(0.45);
ui.load();
setTimeout(ui.loadReferences, 0);
