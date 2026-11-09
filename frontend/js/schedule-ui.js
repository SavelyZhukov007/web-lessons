import { getCategories, getLeaders, getRooms } from './api.js';
import { addDays, dateKey, DAY_NAMES, formatDate, monday, moscowToday, parseDate, scheduleLocation } from './schedule-dates.js';
import { bindDaySwipe, createDayRibbon, stepStudyDay, weekInRange } from './schedule-navigation.js';
import { bindGlassIndicator, mountGlassEverywhere, mountGlassOptics, toggleGlassPanel } from './glass.js';
import { createScheduleFeed, filteredEvents } from './schedule-feed.js';
import { mountLazyScheduleSearch as mountScheduleSearch } from './schedule-search-lazy.js';
import { prefersReducedMotion } from './motion-preferences.js';
import { tapFeedback } from './interaction-feedback.js';

const $ = id => document.getElementById(id);
const FILTERS = [
  ['category_id', 'category', getCategories, 'направлений'],
  ['weekday', 'weekday'],
  ['leader_id', 'leader', getLeaders, 'руководителей'],
  ['room_id', 'room', getRooms, 'аудиторий'],
];
const noEvents = [];
const nowInMoscow = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const compareTime = (a, b) => a.date.localeCompare(b.date) || a.start_time.localeCompare(b.start_time);
const eventFromUrl = () => new URLSearchParams(location.search).get('event')?.slice(0, 160) || null;
const inMyMode = () => window.ItcFeatures?.isMyMode();

export function currentStudyDay() {
  const today = moscowToday();
  return today.getDay() === 0 ? addDays(today, 1) : today;
}

export function mountScheduleUi({ state, render, dayView, onRooms, onPhase, openFilters }) {
  const fields = Object.fromEntries(FILTERS.map(([key, id]) => [key, $(id)]));
  mountGlassEverywhere();
  const feed = createScheduleFeed();
  const panel = $('filter-options');
  const toggle = $('toggle-filters');
  const datePicker = $('week-date');
  const todayButton = $('today');
  const content = $('content');
  const stage = $('schedule-stage');
  const chips = $('filter-chips');
  const next = $('my-next');
  const updateRibbon = createDayRibbon($('day-buttons'), date => goto(date), delta => shiftWeek(delta));
  const view = document.querySelector('.desktop-view');
  const viewIndicator = bindGlassIndicator(view, () => view.querySelector('[aria-pressed="true"]'));
  mountGlassOptics(view);
  mountGlassOptics(panel);
  const search = mountScheduleSearch({ state, filters: fields, jumpTo });
  let linkedEvent = eventFromUrl();
  let pending = linkedEvent;
  let request = 0;
  let references = 0;
  let prefetch;
  let nextKey;
  let chipSignature;
  let flashTimer;
  let raw = noEvents;

  const selectedDate = () => addDays(state.week, state.day);
  const myIds = () => inMyMode() ? new Set(window.ItcFeatures.Follows.all()) : null;
  const hasFilters = () => Object.values(fields).some(input => input.value);
  if (linkedEvent && 'view' in state) state.view = 'list';

  function applyFilters() {
    const events = filteredEvents(raw, fields, myIds());
    const linked = linkedEvent && raw.find(event => event.event_id === linkedEvent && event.date === dateKey(selectedDate()));
    const visible = linked && !events.includes(linked) ? [...events, linked] : events;
    if (visible.length !== state.events.length || visible.some((event, i) => event !== state.events[i])) state.events = visible;
  }

  function remember({ withDay = dayView() || !!fields.weekday.value, event = linkedEvent } = {}) {
    const url = new URL(location.href);
    url.searchParams.set('week', dateKey(state.week));
    if (withDay || event) url.searchParams.set('day', dateKey(selectedDate()));
    else url.searchParams.delete('day');
    if (event) url.searchParams.set('event', event);
    else url.searchParams.delete('event');
    if (url.href !== location.href) history.pushState(null, '', url);
  }

  function goto(date, { withDay, event = null, history: writeHistory = true } = {}) {
    if (!date || !weekInRange(date)) return false;
    if (date.getDay() === 0) {
      date = addDays(date, 1);
      if (!weekInRange(date)) date = addDays(date, -2);
    }
    const previous = selectedDate();
    const week = monday(date);
    const changed = dateKey(week) !== dateKey(state.week);
    state.week = week;
    state.day = date.getDay() - 1;
    linkedEvent = pending = event;
    if (event && 'view' in state) state.view = 'list';
    if (fields.weekday.value) fields.weekday.value = String(state.day + 1);
    if (writeHistory) {
      remember({ withDay, event });
      if (dateKey(date) !== dateKey(previous)) tapFeedback();
    }
    const dir = Math.sign(date - previous);
    if (changed) load({ dir });
    else { applyFilters(); render(dir); }
    return true;
  }

  function jumpTo(event) { goto(parseDate(event.date), { withDay: true, event: event.event_id }); }
  const shiftDay = delta => goto(stepStudyDay(selectedDate(), delta), { withDay: true });
  const shiftWeek = delta => goto(addDays(selectedDate(), delta * 7));

  function prefetchNearby(id) {
    clearTimeout(prefetch);
    if (document.hidden) return;
    prefetch = setTimeout(() => {
      if (id !== request) return;
      feed.prefetch(state.week, () => id === request, updateRibbonAndNext);
    }, 220);
  }

  async function load({ dir = 0, refresh = false } = {}) {
    const id = ++request;
    const week = state.week;
    feed.activate(week);
    const cached = feed.read(week);
    const needsRender = dir || raw !== cached || state.phase !== 'ready';
    raw = cached || noEvents;
    state.phase = cached ? 'ready' : 'loading';
    applyFilters();
    onPhase?.(state.phase);
    if (needsRender) render(dir);
    const hydration = cached ? Promise.resolve() : feed.hydrate(week).then(events => {
      if (id !== request || !events || state.phase !== 'loading') return;
      raw = events; state.phase = 'ready'; applyFilters(); onPhase?.(state.phase); render(dir);
    });
    try {
      const events = await feed.fetchWeek(week, { refresh });
      if (id !== request) return;
      if (raw !== events || state.phase !== 'ready') {
        raw = events;
        state.phase = 'ready';
        applyFilters();
        onPhase?.(state.phase);
        render();
      }
      prefetchNearby(id);
    } catch (error) {
      await hydration;
      if (id !== request || feed.read(week) || error?.name === 'AbortError') return;
      state.phase = 'error';
      state.error = error.message;
      onPhase?.(state.phase);
      render();
    }
  }

  function resetFilters() {
    for (const field of Object.values(fields)) field.value = '';
    applyFilters();
    render();
  }

  function showChips() {
    const active = Object.entries(fields).filter(([, input]) => input.value);
    const signature = JSON.stringify(active.map(([key, input]) => [key, input.value, input.selectedOptions[0]?.textContent]));
    if (signature === chipSignature) return;
    chipSignature = signature;
    const focused = chips.contains(document.activeElement);
    const buttons = active.map(([key, input]) => {
      const label = input.selectedOptions[0].textContent;
      return removableChip(label, () => {
        fields[key].value = '';
        applyFilters();
        render();
      });
    });
    chips.hidden = !buttons.length;
    chips.replaceChildren(...buttons);
    if (focused) (buttons[0] || toggle).focus({ preventScroll: true });
  }

  function removableChip(label, remove) {
    const button = document.createElement('button');
    button.className = 'glass-action';
    button.type = 'button';
    button.textContent = `${label} ×`;
    button.setAttribute('aria-label', `Снять фильтр «${label}»`);
    button.addEventListener('click', remove);
    return button;
  }

  function upcoming(events, start) {
    const now = nowInMoscow.format(new Date());
    const today = dateKey(moscowToday());
    return events.filter(event => event.status !== 'cancelled' && event.date >= start
      && (event.date > today || (event.date === today && event.start_time >= now))).sort(compareTime)[0];
  }

  function showNext() {
    const ids = myIds();
    if (!ids?.size) { next.hidden = true; nextKey = undefined; return; }
    const today = currentStudyDay();
    const first = monday(today);
    const weeks = [first, addDays(first, 7)].filter(weekInRange);
    const start = dateKey(today);
    const available = weeks.flatMap(week => feed.read(week) || noEvents).filter(event => ids.has(event.club_id));
    const event = upcoming(available, start);
    const key = [start, [...ids], event?.event_id, event?.date, event?.start_time, event?.club_name].join('|');
    if (key === nextKey) return;
    nextKey = key;
    next.hidden = !event;
    next.replaceChildren();
    if (event) {
      const button = document.createElement('button');
      button.className = 'glass-action';
      button.type = 'button';
      const label = document.createElement('span');
      label.textContent = `Ближайшее · ${formatDate(parseDate(event.date), { weekday: 'short' })} в ${event.start_time} · ${event.club_name}`;
      button.append(label);
      button.title = label.textContent;
      button.addEventListener('click', () => jumpTo(event));
      next.append(button);
    }
    const id = request;
    for (const week of weeks) {
      if (!feed.read(week) && dateKey(week) !== dateKey(state.week)) {
        feed.fetchWeek(week).then(() => { if (id === request) showNext(); }).catch(() => {});
      }
    }
  }

  function updateRibbonAndNext() {
    if (dayView()) {
      const ids = myIds();
      const events = [-7, 0, 7].flatMap(offset => feed.read(addDays(state.week, offset)) || noEvents);
      updateRibbon(selectedDate(), moscowToday(), filteredEvents(events, fields, ids));
    }
    showNext();
  }

  function updateControls() {
    const date = selectedDate();
    const end = addDays(state.week, 5);
    const start = state.week.getMonth() === end.getMonth() ? state.week.getDate() : formatDate(state.week);
    $('week-label').textContent = `${start} — ${formatDate(end)}`;
    $('week-year').textContent = state.week.getFullYear() === end.getFullYear()
      ? state.week.getFullYear() : `${state.week.getFullYear()} / ${end.getFullYear()}`;
    datePicker.value = dateKey(date);
    $('print-week').href = `/print.html?week=${dateKey(state.week)}`;
    $('prev-week').disabled = !weekInRange(addDays(state.week, -7));
    $('next-week').disabled = !weekInRange(addDays(state.week, 7));
    $('selected-day-label').textContent = `${DAY_NAMES[state.day]}, ${formatDate(date)}`;
    todayButton.setAttribute('aria-pressed', String(dateKey(date) === dateKey(moscowToday())));
    const filterCount = Object.values(fields).filter(input => input.value).length;
    $('reset-filters').disabled = filterCount === 0;
    toggle.querySelector('span').textContent = `Фильтры${filterCount ? ` · ${filterCount}` : ''}`;
    toggle.setAttribute('aria-label', filterCount ? `Фильтры, включено: ${filterCount}` : 'Фильтры');
    if (state.view) {
      $('view-grid').setAttribute('aria-pressed', String(state.view === 'grid'));
      $('view-list').setAttribute('aria-pressed', String(state.view === 'list'));
      viewIndicator();
    }
    showChips();
    updateRibbonAndNext();
    search.render();
  }

  function focusPending(container = content, animation) {
    if (!pending || stage.dataset.searchOpen === 'true' || state.phase !== 'ready') return;
    const element = [...container.querySelectorAll('[data-event-id]')].find(card => card.dataset.eventId === pending);
    if (!element) return;
    const id = pending;
    const focus = () => {
      if (!element.isConnected || linkedEvent !== id || pending !== id) return;
      pending = null;
      element.focus({ preventScroll: true });
      element.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' });
      element.classList.add('itc-flash');
      clearTimeout(flashTimer);
      flashTimer = setTimeout(() => element.classList.remove('itc-flash'), 1750);
    };
    if (animation) animation.finished.then(focus, focus);
    else requestAnimationFrame(focus);
  }

  async function loadReferences() {
    const id = ++references;
    const retry = $('retry-references');
    const defs = FILTERS.filter(([, , load]) => load);
    retry.disabled = true;
    const results = await Promise.allSettled(defs.map(([, , load]) => load()));
    if (id !== references) return;
    const failed = [];
    results.forEach((result, index) => {
      const [key, , , title] = defs[index];
      const select = fields[key];
      const data = result.status === 'fulfilled' ? result.value : null;
      if (!Array.isArray(data) || data.some(item => !Number.isInteger(item.id) || item.id <= 0 || typeof item.name !== 'string')) {
        failed.push(title);
        return;
      }
      if (key === 'room_id') onRooms?.(data);
      const selected = select.value;
      select.replaceChildren(select.options[0], ...data.map(item => new Option(
        key === 'room_id' && item.building ? `${item.name} · ${item.building}` : item.name, item.id)));
      select.value = [...select.options].some(option => option.value === selected) ? selected : '';
      select.disabled = false;
    });
    $('reference-error').hidden = !failed.length;
    $('reference-error').querySelector('span').textContent = `Не удалось загрузить список ${failed.join(', ')}. Доступные фильтры продолжают работать.`;
    retry.disabled = false;
    if (state.phase === 'ready') { applyFilters(); render(); }
  }

  function changeFilters() {
    if (fields.weekday.value && Number(fields.weekday.value) - 1 !== state.day) {
      goto(addDays(state.week, Number(fields.weekday.value) - 1), { withDay: true });
    } else { applyFilters(); render(); }
  }

  $('prev-week').addEventListener('click', () => shiftWeek(-1));
  $('next-week').addEventListener('click', () => shiftWeek(1));
  todayButton.addEventListener('click', () => goto(currentStudyDay()));
  datePicker.addEventListener('change', () => {
    const date = parseDate(datePicker.value);
    if (!date || !datePicker.validity.valid || !goto(date, { withDay: true })) datePicker.value = dateKey(selectedDate());
  });
  toggle.addEventListener('click', () => {
    if (openFilters) { openFilters({ fields, changeFilters, resetFilters, trigger: toggle }); return; }
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    toggleGlassPanel(panel, open);
  });
  for (const [key, field] of Object.entries(fields)) {
    if (key !== 'weekday') field.disabled = true;
    field.addEventListener('change', changeFilters);
  }
  $('reset-filters').addEventListener('click', resetFilters);
  $('retry-references').addEventListener('click', loadReferences);
  $('close-event').addEventListener('click', () => $('event-dialog').close());
  addEventListener('popstate', () => {
    search.close({ restore: false });
    const { week, day } = scheduleLocation(location.search, currentStudyDay());
    goto(addDays(week, day), { history: false, event: eventFromUrl() });
  });
  bindDaySwipe(content, shiftDay, () => dayView() && document.documentElement.dataset.daySwipe !== 'false');
  document.addEventListener('itc:refresh', event => {
    feed.invalidate();
    const result = load({ refresh: true });
    event.detail?.done?.(result);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearTimeout(prefetch); feed.cancelPrefetch(); } else load({ refresh: true });
  });
  window.addEventListener('public:cache-invalidated', () => { feed.invalidate({ persisted: true }); load({ refresh: true }); });
  return { load, loadReferences, updateControls, focusPending, hasFilters, inMyMode, jumpTo, shiftDay, shiftWeek, goto };
}
