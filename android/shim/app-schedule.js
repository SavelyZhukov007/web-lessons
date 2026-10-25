/* Экран «Расписание» в APK (вместо js/schedule.js сайта; подменяется prepare-web.mjs только в www/ приложения).
 * Сайт не меняется. Что иначе, чем на сайте:
 *  - без заголовка «Расписание» и полосы недель; сверху поиск на всю ширину + кнопка-календарь (выбор даты);
 *    ниже «Сегодня», «Мои кружки»/«Отметиться»/колокольчик и кнопка фильтров (иконка, со счётчиком);
 *  - полоса дней Пн–Сб всегда под управлением и прилипает при прокрутке; под ней — диапазон недели «19–24 октября»;
 *  - свайп влево/вправо по списку — следующий/предыдущий день (через границу недели), с анимацией сдвига;
 *    порог по горизонтали + проверка угла, края экрана (жест «Назад» Android) не перехватываются;
 *  - параллельные занятия (одно время) сгруппированы в «слот» с бейджами аудитории и руководителя;
 *  - скорость: память + localStorage (мгновенная отрисовка, потом обновление), предзагрузка соседних недель и каталога,
 *    скелетоны без сдвига вёрстки, обновление карточек по ключу event_id (без перерисовки всего списка).
 * Те же id элементов, что у сайта (#search, #category, #toggle-filters, #content, #day-buttons…), — нативные функции
 * (native-features.js: «Мои кружки», офлайн) работают без изменений. */
import { getSchedule } from './api.js';
import { DAY_NAMES, DAY_SHORT, parseDate, dateKey, addDays, monday, moscowToday, formatDate, minutes } from './schedule-dates.js';
import { icon } from './icons.js';

const $ = s => document.querySelector(s);
const WEEK_MIN = '2000-01-03', WEEK_MAX = '2100-12-27';
const CACHE = 'itc.sched.v1:', CACHE_IDX = 'itc.sched.idx', CACHE_MAX = 16, FRESH_MS = 60e3;
const statusNames = { scheduled: 'По расписанию', moved: 'Перенос', cancelled: 'Отменено' };
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const splash = window.ItcSplash || { progress() {}, done() {} };

let today = moscowToday();
// Воскресенье — занятий нет: «сегодня» = ближайший понедельник
function todayTarget() { today = moscowToday(); return today.getDay() === 0 ? addDays(today, 1) : today; }
const start = todayTarget();
const state = { week: monday(start), day: (start.getDay() + 6) % 7, events: [], phase: 'loading', error: '', filtersOpen: false, key: '' };
window.ItcEvent = id => state.events.find(x => x.event_id === id); // для быстрой отмены/переноса (app-extras)
const mem = new Map(); // ключ запроса → { t, e }
const cards = new Map(); // event_id → { sig, node }
let controller, searchTimer, reqId = 0, firstContent = false;

function node(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

// ---------- разметка экрана (переставляем элементы сайта, id сохраняются) ----------
const main = $('#schedule-main');
const form = $('#schedule-filters');
const fields = { search: $('#search'), category_id: $('#category'), weekday: $('#weekday'), leader_id: $('#leader'), room_id: $('#room') };
const content = $('#content');
const dateInput = $('#week-date');
const todayBtn = $('#today');
const filterBtn = $('#toggle-filters');
const dayButtons = $('#day-buttons');
const status = $('#result-status');

function buildLayout() {
  document.body.classList.add('app-schedule');
  const searchRow = node('div', 'app-search-row');
  const dateBtn = node('button', 'icon-button app-date-btn');
  dateBtn.type = 'button'; dateBtn.id = 'app-date';
  dateBtn.setAttribute('aria-label', 'Выбрать дату');
  dateBtn.append(icon('calendar'));
  dateBtn.addEventListener('click', () => { try { dateInput.showPicker(); } catch { dateInput.focus(); dateInput.click(); } });
  dateInput.classList.add('app-date-input'); dateInput.tabIndex = -1; dateInput.setAttribute('aria-hidden', 'true');
  searchRow.append(form.querySelector('.search-field'), dateBtn, dateInput);
  const row2 = node('div', 'app-row2'); row2.id = 'app-row2';
  todayBtn.textContent = 'Сегодня'; todayBtn.className = 'app-today';
  filterBtn.classList.add('icon-button', 'app-filter-btn');
  filterBtn.querySelector('span')?.classList.add('app-filter-count');
  row2.append(todayBtn, filterBtn);
  fields.search.placeholder = 'Поиск…';
  for (const b of [dateBtn, filterBtn]) b.classList.add('itc-ctl');
  form.prepend(searchRow, row2);
  const days = node('div', 'app-days'); days.id = 'app-days';
  days.append(dayButtons); // подпись диапазона недели убрана: даты видны в полосе дней
  form.closest('.schedule-controls').after(days);
  status.classList.add('visually-hidden');
  days.after(status);
  for (const sel of ['.page-command', '.mobile-days', '.schedule-caption', '.schedule-legend']) $(sel)?.remove();
  content.classList.add('app-content');
}

// ---------- кэш ----------
function filters() { return Object.fromEntries(Object.entries(fields).map(([k, i]) => [k, i.value.trim()])); }
function hasFilters() { return Object.values(filters()).some(Boolean); }
function myKey() { try { return localStorage.getItem('itc.myMode') === '1' ? 'my' + (localStorage.getItem('itc.follows') || '') : ''; } catch { return ''; } }
function keyFor(week) { return dateKey(week) + '|' + JSON.stringify(filters()) + '|' + myKey(); }
function readCache(key) {
  if (mem.has(key)) return mem.get(key);
  try { const v = JSON.parse(localStorage.getItem(CACHE + key)); if (v && Array.isArray(v.e)) { mem.set(key, v); return v; } } catch { /* битый кэш */ }
  return null;
}
function writeCache(key, events) {
  const v = { t: Date.now(), e: events }; mem.set(key, v);
  // в localStorage — только запросы без поиска (поиск по буквам засорил бы хранилище)
  if (filters().search) return;
  try {
    localStorage.setItem(CACHE + key, JSON.stringify(v));
    const idx = (JSON.parse(localStorage.getItem(CACHE_IDX)) || []).filter(k => k !== key); idx.push(key);
    while (idx.length > CACHE_MAX) localStorage.removeItem(CACHE + idx.shift());
    localStorage.setItem(CACHE_IDX, JSON.stringify(idx));
  } catch { /* хранилище заполнено — работаем из памяти */ }
}

function safeEvents(data, week) {
  const tp = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  if (!Array.isArray(data) || data.some(e => !e || typeof e.event_id !== 'string' || !Number.isInteger(e.club_id) || !parseDate(e.date)
    || !tp.test(e.start_time) || !tp.test(e.end_time) || minutes(e.start_time) >= minutes(e.end_time)
    || !['club_name', 'leader_name', 'room_name', 'category_name'].every(k => typeof e[k] === 'string') || !Object.hasOwn(statusNames, e.status))) {
    throw new Error('Сервер вернул расписание в неожиданном формате. Попробуй обновить данные.');
  }
  const first = dateKey(week), last = dateKey(addDays(week, 5));
  return data.filter(e => e.date >= first && e.date <= last);
}

// ---------- загрузка: кэш сразу, сеть потом ----------
async function load({ dir = 0, quiet = false } = {}) {
  clearTimeout(searchTimer);
  controller?.abort();
  controller = new AbortController();
  const id = ++reqId, week = state.week, key = keyFor(week);
  const hit = readCache(key);
  const prevKey = state.key; state.key = key;
  if (hit) { state.events = hit.e; state.phase = 'ready'; }
  else if (!quiet || prevKey !== key) { state.events = []; state.phase = 'loading'; }
  render(dir);
  if (hit && Date.now() - hit.t < FRESH_MS && dir !== 0) { prefetch(); return; } // свежий кэш при листании — без запроса
  splash.progress(0.6);
  try {
    const data = safeEvents(await getSchedule(dateKey(week), filters(), { signal: controller.signal }), week);
    if (id !== reqId) return;
    splash.progress(0.9);
    const changed = !hit || JSON.stringify(hit.e) !== JSON.stringify(data);
    writeCache(key, data);
    if (changed || state.phase !== 'ready') { state.events = data; state.phase = 'ready'; render(0); }
    prefetch();
  } catch (error) {
    if (id !== reqId || error.name === 'AbortError') return;
    if (!hit) { state.phase = 'error'; state.error = error.message; render(0); }
  }
}

let prefetchTimer;
function prefetch() {
  clearTimeout(prefetchTimer);
  prefetchTimer = setTimeout(() => {
    const idle = window.requestIdleCallback || (f => setTimeout(f, 50));
    idle(() => {
      for (const delta of [7, -7]) {
        const w = addDays(state.week, delta); const k = keyFor(w);
        if (dateKey(w) < WEEK_MIN || dateKey(w) > WEEK_MAX) continue;
        const c = readCache(k); if (c && Date.now() - c.t < FRESH_MS) continue;
        getSchedule(dateKey(w), filters()).then(d => writeCache(k, safeEvents(d, w))).catch(() => {});
      }
      if (!sessionStorage.getItem('itc.prefetchedClubs')) { // каталог: страница «Все кружки» откроется из кэша
        sessionStorage.setItem('itc.prefetchedClubs', '1');
        for (const u of ['/api/clubs', '/api/categories']) fetch(u).catch(() => {});
      }
    });
  }, 300);
}

// ---------- отрисовка ----------
function updateControls() {
  const date = addDays(state.week, state.day);
  dateInput.value = dateKey(date);
  const n = Object.entries(filters()).filter(([k, v]) => k !== 'search' && v).length + (myKey() ? 1 : 0); // «Только мои кружки» — тоже фильтр
  const count = filterBtn.querySelector('.app-filter-count');
  if (count) count.textContent = n ? String(n) : '';
  filterBtn.classList.toggle('has-count', n > 0);
  filterBtn.setAttribute('aria-label', (state.filtersOpen ? 'Скрыть фильтры' : 'Фильтры') + (n ? `, включено: ${n}` : ''));
  filterBtn.setAttribute('aria-expanded', String(state.filtersOpen));
  $('#filter-options').hidden = true; // в APK фильтры — только в нижнем листе (filterSheet), страница не сдвигается
  const isToday = dateKey(date) === dateKey(todayTarget());
  todayBtn.setAttribute('aria-pressed', String(isToday));
  [...dayButtons.children].forEach((b, i) => {
    const d = addDays(state.week, i);
    const s = b.firstChild, strong = b.lastChild;
    if (s.textContent !== DAY_SHORT[i]) s.textContent = DAY_SHORT[i];
    if (strong.textContent !== String(d.getDate())) strong.textContent = String(d.getDate());
    b.setAttribute('aria-label', `${DAY_NAMES[i]}, ${formatDate(d)}`);
    b.setAttribute('aria-pressed', String(state.day === i));
    b.classList.toggle('is-today', dateKey(d) === dateKey(today));
  });
}

function sig(e) { return [e.status, e.start_time, e.end_time, e.club_name, e.room_name, e.leader_name, e.category_color, e.date, e.original_date, e.comment].join('\u0001'); }
function anyCard(x) { return x.ghost ? ghostCard(x.e) : card(x); }
function ghostCard(e) {
  const nd = parseDate(e.date), box = node('div', 'calendar-event itc-ghost');
  box.setAttribute('role', 'group'); box.setAttribute('aria-label', `${e.club_name}: перенесено на ${formatDate(nd)}, ${e.start_time}`);
  const time = node('span', 'event-time itc-ghost-time');
  if (e.original_start_time) time.append(node('s', '', `${e.original_start_time}–${e.original_end_time}`)); else time.append(node('s', '', 'обычное время'));
  const go = node('button', 'itc-ghost-link', `Актуальное время: ${formatDate(nd, { weekday: 'short', day: 'numeric', month: 'long' })}, ${e.start_time}`);
  go.type = 'button';
  go.addEventListener('click', () => { window.ItcHaptics?.tap(); jumpTo(e); });
  box.append(time, node('strong', 'event-name', e.club_name), node('span', 'event-badge', 'Перенесено'), go);
  return box;
}
// перейти к дню переноса в ленте дней, прокрутить к занятию и коротко подсветить его
function jumpTo(e) {
  goto(parseDate(e.date));
  const t0 = performance.now();
  (function find() {
    const el = state.phase === 'ready' && pane && pane.querySelector(`.calendar-event[data-event-id="${CSS.escape(e.event_id)}"]`);
    if (!el) { if (performance.now() - t0 < 3000) requestAnimationFrame(find); return; }
    setTimeout(() => {
      el.scrollIntoView({ behavior: reduced.matches ? 'auto' : 'smooth', block: 'center' });
      el.classList.remove('itc-flash'); void el.offsetWidth; el.classList.add('itc-flash');
      setTimeout(() => el.classList.remove('itc-flash'), 1800);
    }, reduced.matches ? 0 : 260);
  })();
}
function card(e) {
  const s = sig(e), c = cards.get(e.event_id);
  if (c && c.sig === s) { c.event = e; return c.node; }
  const b = node('button', `calendar-event ${e.status}${e.status !== 'scheduled' ? ' has-status' : ''}`);
  b.type = 'button'; b.dataset.eventId = e.event_id;
  b.style.setProperty('--event-color', /^#[\da-f]{6}$/i.test(e.category_color) ? e.category_color : '#606963');
  b.setAttribute('aria-label', `${e.club_name}. ${formatDate(parseDate(e.date))}, ${e.start_time}–${e.end_time}. ${e.room_name}. ${e.leader_name}. ${statusNames[e.status]}. Открыть подробности.`);
  const time = node('span', 'event-time');
  time.append(node('span', 'event-start', e.start_time), node('span', 'time-divider', '–'), node('span', 'event-end', e.end_time));
  b.append(time, node('strong', 'event-name', e.club_name), node('span', 'event-room', e.room_name), node('span', 'event-leader', e.leader_name));
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
  if (state.phase === 'error') return [emptyState('Не получилось загрузить расписание', state.error, { label: 'Повторить попытку', run: () => load() })];
  const key = dateKey(addDays(state.week, state.day));
  // t102: перенесённое занятие оставляет в старом слоте приглушённую карточку «Перенесено» → «Актуальное время»
  const ghosts = state.events.filter(e => e.status === 'moved' && e.original_date === key && (e.date !== key || (e.original_start_time && e.original_start_time !== e.start_time)))
    .map(e => ({ ghost: true, e, start_time: e.original_start_time || '', end_time: e.original_end_time || '', club_name: e.club_name }));
  const daily = state.events.filter(e => e.date === key).concat(ghosts)
    .sort((a, b) => a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time) || a.club_name.localeCompare(b.club_name, 'ru'));
  if (!daily.length) {
    if (hasFilters()) return [emptyState('Ничего не нашлось', 'Попробуй другое сочетание фильтров или сбрось их.', { label: 'Сбросить фильтры', run: resetFilters })];
    if (myKey()) return [emptyState('В «Моих кружках» занятий нет', 'В этот день у отмеченных кружков ничего нет. Смахни влево — следующий день, или выключи «Мои кружки».')];
    return [emptyState('Занятий нет', 'В этот день кружков нет. Смахни влево или вправо, чтобы посмотреть соседние дни.')];
  }
  const out = [];
  // карточка «Сейчас/Далее» убрана с экрана по просьбе пользователя (t93); nowCard() оставлен для виджета
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
// «Сейчас / Далее» (только для сегодняшнего дня по Москве)
function nowCard(key, daily) {
  if (key !== dateKey(moscowToday())) return null;
  const m = new Date(Date.now() + (new Date().getTimezoneOffset() + 180) * 60000), now = m.getHours() * 60 + m.getMinutes();
  const live = daily.filter(e => e.status !== 'cancelled');
  const cur = live.filter(e => minutes(e.start_time) <= now && now < minutes(e.end_time));
  const next = live.find(e => minutes(e.start_time) > now);
  if (!cur.length && !next) return null;
  const box = node('section', 'app-now'); box.setAttribute('aria-label', 'Сейчас и далее');
  const row = (label, e, extra) => {
    const b = node('button', 'app-now-row'); b.type = 'button';
    b.append(node('span', 'app-now-label', label), node('strong', 'app-now-title', e.club_name), node('span', 'app-now-meta', [extra, e.room_name].filter(Boolean).join(' · ')));
    b.addEventListener('click', () => { const c = content.querySelector(`[data-event-id="${CSS.escape(e.event_id)}"]`); c?.scrollIntoView({ behavior: 'smooth', block: 'center' }); c?.focus({ preventScroll: true }); });
    return b;
  };
  for (const e of cur.slice(0, 2)) box.append(row('Сейчас', e, `до ${e.end_time}`));
  if (next) { const d = minutes(next.start_time) - now; box.append(row('Далее', next, d < 60 ? `через ${d} мин, в ${next.start_time}` : `в ${next.start_time}`)); }
  return box;
}
document.addEventListener('itc:refresh', e => { mem.clear(); const p = load({ quiet: true }); e.detail?.done?.(p); });
setInterval(() => { const old = content.querySelector('.app-now'); if (!old || document.hidden) return;
  const key = dateKey(addDays(state.week, state.day)); const n = nowCard(key, state.events.filter(x => x.date === key).sort((a, b) => a.start_time.localeCompare(b.start_time)));
  if (n) old.replaceWith(n); else old.remove(); }, 60000);
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
  updateControls(); setStatus();
  content.setAttribute('aria-busy', String(state.phase === 'loading'));
  const kids = dayChildren();
  if (!pane || !pane.isConnected) { pane = node('div', 'app-pane'); content.replaceChildren(pane); }
  if (dir && !reduced.matches && pane.childElementCount) slide(kids, dir);
  else {
    // по ключу: те же узлы карточек переиспользуются, меняется только то, что изменилось
    const same = kids.length === pane.children.length && kids.every((k, i) => k === pane.children[i]);
    if (!same) pane.replaceChildren(...kids);
  }
  if (state.phase === 'ready' || state.phase === 'error') contentReady();
}
function slide(kids, dir, from = 0) {
  if (animating) animating.finish();
  const old = pane, w = content.clientWidth || innerWidth;
  const next = node('div', 'app-pane'); next.append(...kids);
  content.style.minHeight = old.offsetHeight + 'px';
  old.classList.add('app-pane-out'); content.append(next); pane = next;
  const opts = { duration: 240, easing: 'cubic-bezier(.2,.8,.2,1)' };
  const a1 = old.animate([{ transform: `translateX(${from}px)` }, { transform: `translateX(${-dir * w * 0.35}px)`, opacity: 0 }], opts);
  const a2 = next.animate([{ transform: `translateX(${dir * w + from}px)`, opacity: 0.4 }, { transform: 'none', opacity: 1 }], opts);
  animating = a2;
  const end = () => { old.remove(); content.style.minHeight = ''; if (animating === a2) animating = null; };
  a2.finished.then(end, end); a1.finished.catch(() => {});
}
function contentReady() {
  if (firstContent) return; firstContent = true;
  window.ItcPerf = Object.assign(window.ItcPerf || {}, { firstContent: performance.now() });
  splash.progress(1); splash.done();
}

// ---------- навигация по дням/неделям ----------
function canWeek(delta) { const k = dateKey(addDays(state.week, delta * 7)); return k >= WEEK_MIN && k <= WEEK_MAX; }
function goto(date, dir) {
  const week = monday(date), day = Math.min((date.getDay() + 6) % 7, 5);
  if (dateKey(week) < WEEK_MIN || dateKey(week) > WEEK_MAX) return;
  const weekChanged = dateKey(week) !== dateKey(state.week);
  if (dir === undefined) dir = Math.sign(addDays(week, day) - addDays(state.week, state.day));
  if (!weekChanged && day === state.day) { render(0); return; }
  state.week = week; state.day = day;
  if (fields.weekday.value) fields.weekday.value = String(day + 1);
  if (weekChanged || fields.weekday.value) load({ dir }); else render(dir);
}
function shiftDay(delta) {
  let day = state.day + delta, week = state.week;
  if (day > 5) { if (!canWeek(1)) return false; day = 0; week = addDays(week, 7); }
  if (day < 0) { if (!canWeek(-1)) return false; day = 5; week = addDays(week, -7); }
  goto(addDays(week, day), delta);
  return true;
}
function shiftWeek(delta) { if (canWeek(delta)) goto(addDays(state.week, delta * 7 + state.day), delta); }
function resetFilters() {
  for (const i of Object.values(fields)) i.value = '';
  try { if (localStorage.getItem('itc.myMode') === '1') { localStorage.setItem('itc.myMode', '0'); document.dispatchEvent(new CustomEvent('itc:follows')); } } catch { /* нет хранилища */ }
  updateControls(); load();
}

// ---------- свайп между днями ----------
function wireSwipe() {
  const EDGE = 24, LOCK = 10, MIN = 56, VEL = 0.35;
  let sx = 0, sy = 0, st = 0, mode = '', dx = 0;
  content.style.touchAction = 'pan-y';
  content.addEventListener('touchstart', e => {
    if (e.touches.length !== 1 || animating) { mode = 'none'; return; }
    const t = e.touches[0]; sx = t.clientX; sy = t.clientY; st = e.timeStamp; dx = 0;
    mode = sx < EDGE || sx > innerWidth - EDGE ? 'none' : ''; // края — системный жест «Назад»
  }, { passive: true });
  content.addEventListener('touchmove', e => {
    if (mode === 'none' || mode === 'v') return;
    const t = e.touches[0], x = t.clientX - sx, y = t.clientY - sy;
    if (!mode) {
      if (Math.abs(x) < LOCK && Math.abs(y) < LOCK) return;
      mode = Math.abs(x) > Math.abs(y) * 1.4 ? 'h' : 'v'; // угол < ~35° к горизонтали
      if (mode === 'v') return;
    }
    dx = x;
    const edge = (x < 0 && state.day === 5 && !canWeek(1)) || (x > 0 && state.day === 0 && !canWeek(-1));
    pane.style.transform = `translateX(${edge ? x * 0.25 : x * 0.9}px)`;
  }, { passive: true });
  const end = e => {
    if (mode !== 'h') { mode = ''; return; }
    mode = '';
    const v = Math.abs(dx) / Math.max(1, e.timeStamp - st);
    const from = dx * 0.9;
    if ((Math.abs(dx) > MIN || (v > VEL && Math.abs(dx) > 24))) {
      const dir = dx < 0 ? 1 : -1;
      pane.style.transform = '';
      swipeFrom = from;
      if (shiftDay(dir)) return;
    }
    const p = pane; p.style.transform = '';
    if (p.animate && !reduced.matches) p.animate([{ transform: `translateX(${from}px)` }, { transform: 'none' }], { duration: 180, easing: 'ease-out' });
  };
  content.addEventListener('touchend', end);
  content.addEventListener('touchcancel', end);
}
let swipeFrom = 0;
const baseSlide = slide;
// продолжаем анимацию с той точки, где отпустили палец
// eslint-disable-next-line no-func-assign
slide = (kids, dir) => { const f = swipeFrom; swipeFrom = 0; baseSlide(kids, dir, f); };

// ---------- подробности ----------
function details(e) {
  const t = $('#event-details'); t.replaceChildren();
  t.append(node('p', `event-badge ${e.status}`, statusNames[e.status]));
  const title = node('h2', '', e.club_name); title.id = 'event-title'; t.append(title);
  const dl = node('dl', 'event-facts');
  const facts = [['Когда', `${formatDate(parseDate(e.date), { year: 'numeric' })}, ${e.start_time}–${e.end_time}`], ['Аудитория', e.room_name], ['Руководитель', e.leader_name], ['Направление', e.category_name]];
  if (e.status === 'moved' && parseDate(e.original_date)) facts.push(['Исходная дата', formatDate(parseDate(e.original_date), { year: 'numeric' })]);
  const same = state.events.filter(x => x.event_id !== e.event_id && x.date === e.date && x.status !== 'cancelled' && minutes(x.start_time) < minutes(e.end_time) && minutes(e.start_time) < minutes(x.end_time));
  if (same.length) facts.push(['Параллельно', same.map(x => `${x.club_name} (${x.room_name})`).join(', ')]);
  for (const [k, v] of facts) dl.append(node('dt', '', k), node('dd', '', v));
  t.append(dl);
  if (e.comment) t.append(node('p', 'event-comment', e.comment));
  const a = node('a', 'club-link', 'О кружке'); a.append(icon('arrow')); a.href = `/club.html?id=${e.club_id}`; t.append(a);
  const dlg = $('#event-dialog'); if (!dlg.open) dlg.showModal();
}

// ---------- события ----------
buildLayout();
for (let d = 0; d < 6; d++) {
  const b = node('button'); b.type = 'button'; b.append(node('span'), node('strong'));
  b.addEventListener('click', () => goto(addDays(state.week, d)));
  dayButtons.append(b);
}
todayBtn.addEventListener('click', () => goto(todayTarget()));
dateInput.addEventListener('change', () => { const d = parseDate(dateInput.value); if (d && dateInput.validity.valid) goto(d.getDay() === 0 ? addDays(d, 1) : d); else updateControls(); });
filterBtn.addEventListener('click', () => filterSheet());
document.addEventListener('itc:mymode', () => updateControls());
form.addEventListener('submit', ev => { ev.preventDefault(); load(); });
fields.search.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => load({ quiet: true }), 250); });
for (const [k, f] of Object.entries(fields)) {
  if (k === 'search') continue;
  f.addEventListener('change', () => { if (k === 'weekday' && f.value) state.day = Number(f.value) - 1; load({ quiet: true }); });
}
$('#reset-filters').addEventListener('click', resetFilters);

// ---------- нижний лист фильтров (t96): свои чипы вместо системных select, «Сбросить» / «Показать», свайп вниз и «Назад» закрывают
function filterSheet() {
  if (document.querySelector('.itc-fsheet')) return;
  const GROUPS = [['category_id', 'Направление'], ['weekday', 'День'], ['leader_id', 'Руководитель'], ['room_id', 'Аудитория']];
  const pending = Object.fromEntries(GROUPS.map(([k]) => [k, fields[k].value]));
  const wrap = node('div', 'itc-fsheet'); wrap.setAttribute('role', 'dialog'); wrap.setAttribute('aria-modal', 'true'); wrap.setAttribute('aria-label', 'Фильтры');
  const panel = node('div', 'itc-fsheet-panel'), handle = node('div', 'itc-fsheet-handle'), head = node('h2', '', 'Фильтры'), body = node('div', 'itc-fsheet-body');
  handle.setAttribute('aria-hidden', 'true');
  const mine = $('#itc-my-toggle'), mineHome = mine?.parentNode, mineNext = mine?.nextSibling;
  if (mine) body.append(mine);
  for (const [k, title] of GROUPS) {
    const sel = fields[k]; if (!sel) continue;
    const sec = node('section', 'itc-fgroup'); sec.append(node('h3', '', title));
    const list = node('div', 'itc-fchips'); list.setAttribute('role', 'radiogroup'); list.setAttribute('aria-label', title);
    for (const o of sel.options) {
      const c = node('button', 'itc-fchip', o.value ? o.textContent : 'Все'); c.type = 'button'; c.setAttribute('role', 'radio'); c.dataset.v = o.value;
      c.setAttribute('aria-checked', String(pending[k] === o.value));
      c.addEventListener('click', () => { pending[k] = o.value; for (const x of list.children) x.setAttribute('aria-checked', String(x.dataset.v === o.value)); window.ItcHaptics?.tap(); });
      list.append(c);
    }
    sec.append(list); body.append(sec);
  }
  const foot = node('div', 'itc-fsheet-foot'), reset = node('button', 'itc-fbtn', 'Сбросить'), show = node('button', 'itc-fbtn primary', 'Показать');
  reset.type = show.type = 'button'; foot.append(reset, show);
  panel.append(handle, head, body, foot); wrap.append(panel); document.body.append(wrap);
  document.documentElement.classList.add('itc-fsheet-open');
  requestAnimationFrame(() => wrap.classList.add('in'));
  history.pushState({ itcSheet: 1 }, '');
  let closed = false;
  function close(fromBack) {
    if (closed) return; closed = true;
    if (mine && mineHome) mineHome.insertBefore(mine, mineNext);
    wrap.classList.remove('in'); panel.style.transform = ''; document.documentElement.classList.remove('itc-fsheet-open');
    setTimeout(() => wrap.remove(), 280); removeEventListener('popstate', onPop);
    if (!fromBack && history.state?.itcSheet) history.back();
    filterBtn.focus({ preventScroll: true });
  }
  function onPop() { close(true); }
  addEventListener('popstate', onPop);
  wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
  wrap.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  show.addEventListener('click', () => {
    let changed = false;
    for (const [k] of GROUPS) if (fields[k].value !== pending[k]) { fields[k].value = pending[k]; changed = true; if (k === 'weekday' && pending[k]) state.day = Number(pending[k]) - 1; }
    close(); updateControls(); if (changed) load({ quiet: true });
  });
  reset.addEventListener('click', () => { close(); resetFilters(); });
  // свайп вниз за ручку/шапку или когда список прокручен к началу
  let y0 = null, dy = 0;
  panel.addEventListener('touchstart', e => { if (body.contains(e.target) && body.scrollTop > 0) return; y0 = e.touches[0].clientY; dy = 0; panel.style.transition = 'none'; }, { passive: true });
  panel.addEventListener('touchmove', e => { if (y0 == null) return; dy = Math.max(0, e.touches[0].clientY - y0); panel.style.transform = `translateY(${dy}px)`; }, { passive: true });
  panel.addEventListener('touchend', () => { if (y0 == null) return; panel.style.transition = ''; y0 = null; if (dy > 90) close(); else panel.style.transform = ''; });
  setTimeout(() => show.focus({ preventScroll: true }), 300);
}
$('#close-event').addEventListener('click', () => $('#event-dialog').close());
// справочники фильтров — из кэша сразу, потом из сети (как и было на сайте)
async function loadReferences() {
  const api = await import('./api.js');
  const defs = [['category_id', api.getCategories], ['leader_id', api.getLeaders], ['room_id', api.getRooms]];
  const res = await Promise.allSettled(defs.map(([, g]) => g()));
  const failed = [];
  res.forEach((r, i) => {
    const sel = fields[defs[i][0]];
    const data = r.status === 'fulfilled' ? r.value : null;
    if (!Array.isArray(data)) { failed.push(i); return; }
    const v = sel.value; sel.replaceChildren(sel.options[0]);
    for (const it of data) { const o = node('option', '', defs[i][0] === 'room_id' && it.building ? `${it.name} · ${it.building}` : it.name); o.value = String(it.id); sel.append(o); }
    sel.value = v; sel.disabled = false;
  });
  $('#reference-error').hidden = !failed.length;
  $('#reference-error span').textContent = failed.length ? 'Не все фильтры загрузились. Остальные работают.' : '';
}
$('#retry-references').addEventListener('click', loadReferences);
document.addEventListener('visibilitychange', () => { // вернулись на следующий день — «сегодня» пересчитывается
  if (document.hidden) return;
  const prev = dateKey(today); today = moscowToday();
  if (prev !== dateKey(today)) updateControls();
  load({ quiet: true });
});
wireSwipe();
window.ItcSchedule = { shiftDay, shiftWeek, goto: d => goto(parseDate(d)), state };
splash.progress(0.45);
load();
setTimeout(loadReferences, 0);
