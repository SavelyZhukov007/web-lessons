import { bindGlassIndicator, mountGlassOptics } from './glass.js';
import { prefersReducedMotion } from './motion-preferences.js';
import { addDays, dateKey, formatDate, parseDate } from './schedule-dates.js';
import { prepareScheduleSearch } from './schedule-search-index.js';

const RECENT_KEY = 'clubs.scheduleSearch.v1';
const $ = id => document.getElementById(id);

function node(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text) element.textContent = text;
  return element;
}

function recentQueries() {
  try {
    const data = JSON.parse(localStorage.getItem(RECENT_KEY));
    return Array.isArray(data) ? data.filter(value => typeof value === 'string').slice(0, 5) : [];
  } catch { return []; }
}

function saveRecent(queries) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(queries)); } catch { /* search still works */ }
}

export function mountScheduleSearch({ state, filters, jumpTo }) {
  const form = $('schedule-filters');
  const input = $('search');
  const exit = $('search-exit');
  const overview = $('schedule-overview');
  const panel = $('schedule-search-view');
  const stage = $('schedule-stage');
  const status = $('search-status');
  const results = $('search-results');
  const scopes = $('search-scope');
  const updateScope = bindGlassIndicator(scopes, () => scopes.querySelector('[aria-pressed="true"]'));
  mountGlassOptics(scopes);
  let scope = 'day';
  let opened = false;
  let composing = false;
  let scroll = 0;
  let transitions = [];
  let searched;
  let model;
  let pending;
  let indexedEvents;
  let lookup;

  function switchView(visible, exiting) {
    for (const animation of transitions) animation.cancel();
    visible.classList.remove('is-fading');
    visible.hidden = false;
    visible.inert = false;
    exiting.inert = true;
    stage.dataset.searchOpen = String(opened);
    if (prefersReducedMotion() || !visible.animate) { exiting.hidden = true; return; }
    exiting.classList.add('is-fading');
    const enter = visible.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }],
      { duration: 190, easing: 'ease-out' });
    const fade = exiting.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: 'ease-out' });
    transitions = [enter, fade];
    fade.finished.then(() => {
      if (fade !== transitions[1]) return;
      if (exiting.inert) exiting.hidden = true;
      exiting.classList.remove('is-fading');
    }, () => {});
  }

  function open() {
    if (opened) return;
    opened = true;
    scope = 'day';
    paintScope();
    scroll = window.scrollY;
    exit.hidden = false;
    switchView(panel, overview);
    updateScope();
    if (scroll > form.offsetTop) form.scrollIntoView({ block: 'start' });
    render();
  }

  function close({ restore = true } = {}) {
    if (!opened) return false;
    opened = false;
    if (panel.contains(document.activeElement) || document.activeElement === exit || document.activeElement === input) {
      form.tabIndex = -1;
      form.focus({ preventScroll: true });
    }
    exit.hidden = true;
    input.value = '';
    searched = null;
    switchView(overview, panel);
    if (restore) requestAnimationFrame(() => { if (!opened) window.scrollTo(0, scroll); });
    return true;
  }

  function remember() {
    const text = input.value.trim();
    if (text) saveRecent([text, ...recentQueries().filter(query => query.toLowerCase() !== text.toLowerCase())].slice(0, 5));
  }

  function showRecent() {
    const hints = node('p', 'search-hint', 'Введи название кружка, имя руководителя или номер аудитории. Поиск понимает опечатки, транслит и другую раскладку.');
    const recent = recentQueries();
    results.replaceChildren(hints);
    if (!recent.length) return;
    const head = node('div', 'search-recent-heading');
    const clear = node('button', 'glass-action', 'Очистить');
    clear.type = 'button';
    clear.onclick = () => { saveRecent([]); render(); input.focus({ preventScroll: true }); };
    head.append(node('h3', '', 'Недавние запросы'), clear);
    const chips = node('div', 'search-recent');
    for (const query of recent) {
      const button = node('button', 'glass-action', query);
      button.type = 'button';
      button.onclick = () => { input.value = query; input.focus({ preventScroll: true }); render(); };
      chips.append(button);
    }
    results.append(head, chips);
  }

  function render() {
    if (!opened || composing) return;
    const query = input.value.trim();
    const { day, week, events, phase } = state;
    const date = addDays(week, day);
    const dateLabel = formatDate(date, { weekday: 'long' });
    const period = scope === 'day' ? dateLabel : `${formatDate(week)} — ${formatDate(addDays(week, 5))}`;
    if (!query) {
      status.textContent = period;
      showRecent();
      return;
    }
    if (!model && !pending) {
      pending = import('./schedule-search-model.js').then(module => { model = module; }, () => {})
        .finally(() => { pending = null; if (model) render(); else if (opened) status.textContent = 'Поиск не загрузился. Обнови страницу и попробуй ещё раз.'; });
    }
    if (!model || phase !== 'ready') {
      status.textContent = phase === 'error' ? 'Расписание для поиска недоступно. Закрой поиск и повтори загрузку.' : 'Подготавливаем поиск…';
      results.replaceChildren();
      return;
    }
    if (indexedEvents !== events) {
      indexedEvents = events; lookup = null;
      prepareScheduleSearch(events).then(index => { if (indexedEvents === events) { lookup = index; render(); } }, () => { if (opened) status.textContent = 'Не удалось подготовить поиск. Попробуй ещё раз.'; });
    }
    if (!lookup) { status.textContent = 'Подготавливаем поиск…'; return; }
    const key = [query, scope, dateKey(date), events, filters.weekday.value];
    if (searched && key.every((value, index) => value === searched[index])) return;
    searched = key;
    const hits = lookup(query, scope === 'day' ? dateKey(date) : '').filter(hit => {
      const date = parseDate(hit.event.date);
      const dayOfWeek = date.getDay();
      return hit.event.date >= dateKey(week) && hit.event.date <= dateKey(addDays(week, 5))
        && (!filters.weekday.value || dayOfWeek === Number(filters.weekday.value));
    });
    status.textContent = `${period} · ${hits.length ? `найдено: ${hits.length}` : 'ничего не нашлось'}`;
    results.replaceChildren();
    if (!hits.length) {
      results.append(node('p', 'search-hint', scope === 'day'
        ? 'Попробуй другой запрос или выбери «Вся неделя».'
        : 'Попробуй другой запрос или открой каталог кружков.'));
      return;
    }
    const list = node('ul', 'search-result-list');
    for (const { event, terms } of hits) {
      const button = node('button', 'search-result');
      button.type = 'button';
      const time = node('span', 'search-result-time', `${formatDate(parseDate(event.date), { weekday: 'short' })} · ${event.start_time}`);
      const name = node('strong', 'search-result-name');
      name.append(model.markedText(event.club_name, terms));
      const meta = node('span', 'search-result-meta');
      const description = [...(event.room_names || [event.room_name]), ...(event.leader_names || [event.leader_name])].filter(Boolean).join(' · ');
      meta.append(model.markedText(description, terms));
      button.append(time, name, meta);
      const label = { cancelled: 'Отменено', moved: 'Перенос' }[event.status];
      if (label) button.append(node('span', `event-badge ${event.status}`, label));
      button.onclick = () => { remember(); close({ restore: false }); jumpTo(event); };
      const item = document.createElement('li');
      item.append(button);
      list.append(item);
    }
    results.append(list);
  }

  function updateInput() { searched = null; open(); render(); }
  input.addEventListener('focus', open);
  input.addEventListener('click', open);
  input.addEventListener('input', event => { if (!event.isComposing && !composing) updateInput(); });
  input.addEventListener('compositionstart', () => { composing = true; });
  input.addEventListener('compositionend', () => { composing = false; if (opened) updateInput(); });
  input.addEventListener('search', () => { if (opened && !composing) updateInput(); });
  input.addEventListener('keydown', event => {
    if (event.key !== 'ArrowDown') return;
    const first = results.querySelector('button');
    if (first) { event.preventDefault(); first.focus(); }
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (composing) return;
    open();
    remember();
    input.blur();
  });
  input.addEventListener('beforeinput', event => {
    if (composing || !['insertLineBreak', 'insertParagraph'].includes(event.inputType)) return;
    event.preventDefault();
    form.requestSubmit();
  });
  exit.addEventListener('click', () => close());
  $('schedule-main').addEventListener('keydown', event => {
    if (event.key === 'Escape' && !event.isComposing && close()) event.preventDefault();
  });
  function paintScope() {
    for (const button of scopes.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.searchScope === scope));
    updateScope();
  }
  scopes.addEventListener('click', event => {
    const button = event.target.closest('[data-search-scope]');
    if (!button) return;
    scope = button.dataset.searchScope;
    paintScope();
    render();
  });
  return { render, close, open, setComposing(value) { composing = value; } };
}
