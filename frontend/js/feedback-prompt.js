// Карточка «Как тебе KipClub?» внизу экрана (не модальная: расписание остаётся доступным). Правила: feedback-prompt-logic.js.
// Сигналы: открытия, дни с расписанием (kc:schedule-view), экспорт в календарь, «Мои кружки», ошибки загрузки (kc:load-error) и JS.
// При выключенной статистике карточка может показываться, но счётчики fb_* не уходят (KipUsage.emit сам их гасит).
import * as P from './feedback-prompt-logic.js';

const launchedAt = Date.now();
let card, timer;
const storage = (() => { try { return window.localStorage; } catch { return null; } })();
const version = () => String(window.ITC_VERSION || window.KipUsage?.version?.() || '').replace(/^v/, '');
const update = fn => { if (!storage) return null; const next = fn(P.load(storage)); P.save(storage, next); return next; };
const emit = (metric, dim) => { try { window.KipUsage?.emit(metric, dim); } catch { /* статистика не мешает */ } };

function page() {
  const path = location.pathname;
  if (/^\/admin(?:\/|$)/.test(path)) return 'admin';
  if (path === '/' || path === '/index.html') return 'home';
  return /^\/(?:ios|android|install)/.test(path) ? 'install' : 'other';
}
function busy() {
  const active = document.activeElement;
  return !!document.querySelector('dialog[open], #itc-sheet, .search-overlay:not([hidden]), [data-search-open], .is-searching, .storage-notice, .fb-prompt')
    || !!(active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) || document.hidden;
}
function iosSafariWeb() {
  const ua = navigator.userAgent || '';
  const ios = /iP(hone|ad|od)/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios && !navigator.standalone && !window.Capacitor?.isNativePlatform?.();
}
const whatsNewSeen = () => { try { return localStorage.getItem(`kipclub.release.seen.v${version()}`) === '1'; } catch { return false; } };
export function context(now = Date.now()) {
  return { now, online: navigator.onLine !== false, busy: busy(), admin: page() === 'admin', sinceLaunchMs: now - launchedAt,
    page: page(), iosSafari: iosSafariWeb(), whatsNewSeen: whatsNewSeen() };
}

async function openForm(opts) {
  const { openFeedback } = await import('./feedback.js');
  openFeedback(document.querySelector('[data-settings-button]'), opts);
}

function close() { card?.remove(); card = null; }

export function showPrompt(source = 'prompt_usage', { force = false } = {}) {
  if (card || (!force && !storage)) return false;
  const now = Date.now();
  update(s => P.markShown(s, now, source));
  emit('fb_prompt_shown', source);
  const title = P.COPY[source] || P.COPY.prompt_usage;
  const later = h('button', { type: 'button', class: 'btn btn--text btn--small fb-prompt-close', 'aria-label': P.COPY.later }, '×');
  later.addEventListener('click', () => { update(s => P.snooze(s, Date.now())); emit('fb_prompt_snooze', source); close(); });
  card = h('aside', { class: 'fb-prompt', role: 'region', 'aria-label': 'Оценка KipClub', 'data-source': source });
  const body = h('div', { class: 'fb-prompt-body' });
  card.append(h('div', { class: 'fb-prompt-head' }, h('p', { class: 'fb-prompt-title', id: 'fb-prompt-title' }, title), later), body);
  if (source === 'prompt_error') {
    body.append(actions(() => { close(); openForm({ type: 'bug', source }); }, () => { update(s => P.snooze(s, Date.now())); emit('fb_prompt_dismiss', source); close(); }, P.COPY.later));
  } else {
    const faces = h('div', { class: 'fb-prompt-faces', role: 'group', 'aria-labelledby': 'fb-prompt-title' },
      P.FACES.map(([value, face, label]) => {
        const b = h('button', { type: 'button', class: 'fb-face', 'aria-label': label, title: label }, face);
        b.addEventListener('click', () => rate(value, source, body));
        return b;
      }));
    body.append(faces);
  }
  document.body.append(card);
  return true;
}

function actions(onWrite, onNo, noLabel = P.COPY.no) {
  const write = h('button', { type: 'button', class: 'btn btn--filled btn--small' }, P.COPY.write);
  const no = h('button', { type: 'button', class: 'btn btn--text btn--small' }, noLabel);
  write.addEventListener('click', onWrite); no.addEventListener('click', onNo);
  return h('div', { class: 'fb-prompt-actions' }, no, write);
}

function rate(value, source, body) {
  emit('fb_rating', value); // оценка уходит сразу и без текста, даже если человек не будет писать
  update(P.rated);
  card.querySelector('.fb-prompt-title').textContent = P.followUp(value);
  body.replaceChildren(actions(() => { close(); openForm({ type: P.typeForRating(value), rating: value, source }); },
    () => { emit('fb_prompt_dismiss', source); close(); }));
  body.querySelector('.btn--filled')?.focus({ preventScroll: true });
}

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const c of children.flat()) el.append(c);
  return el;
}

export function maybeShow() {
  if (!storage || card) return false;
  const state = P.load(storage);
  const source = P.decide(state, context());
  return source ? showPrompt(source) : false;
}

function schedule(delay = 12e3) { clearTimeout(timer); timer = setTimeout(() => { if (!maybeShow()) schedule(30e3); }, delay); }

if (typeof window !== 'undefined' && storage && page() !== 'admin' && !window.__kcFeedbackPrompt) {
  window.__kcFeedbackPrompt = true;
  let fresh = true; // одно открытие на сессию, а не на каждую страницу сайта
  try { fresh = !sessionStorage.getItem('kc.fbOpen'); sessionStorage.setItem('kc.fbOpen', '1'); } catch { /* без sessionStorage считаем каждую загрузку */ }
  if (fresh) update(s => P.recordOpen(s, { now: Date.now(), version: version() }));
  window.addEventListener('kc:schedule-view', () => update(s => P.recordScheduleDay(s, Date.now())));
  window.addEventListener('kc:load-error', () => update(P.recordError));
  window.addEventListener('error', event => { if (event.error) update(P.recordError); });
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href*="calendar.ics"], [data-usage^="calendar_export"]');
    if (link) update(P.recordCalendar);
    if (event.target.closest?.('[data-usage="fav_add"]')) update(P.recordFav);
  }, { capture: true, passive: true });
  window.addEventListener('kc:fav-add', () => update(P.recordFav));
  window.addEventListener('kc:calendar-export', () => update(P.recordCalendar));
  if (page() === 'home') schedule();
  window.KipFeedbackPrompt = { maybeShow, showPrompt };
}
