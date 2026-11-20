// Карточка «Как тебе KipClub?»: когда показывать, лимиты и пауза. Чистая логика без DOM (frontend/tests/feedback-prompt.test.mjs).
// Состояние хранится только на устройстве (localStorage), на сервер уходят лишь анонимные счётчики fb_*.
'use strict';

export const STATE_KEY = 'kc.fbPrompt.v1';
export const DAY = 864e5;
export const RULES = {
  minOpens: 4,              // никогда в первые 3 открытия
  minSinceLaunchMs: 10e3,   // и не в первые 10 секунд после запуска
  usageDays: 5, usageAgeDays: 7, // 5 дней с расписанием и не раньше 7 дней с первого запуска
  calendarExports: 2, favAdds: 3,
  updateAgeDays: 2, updateOpens: 2,
  gapDays: 30, perYear: 4,  // не чаще раза в 30 дней и не больше 4 раз в год
  snoozeDays: [30, 90],     // «Не сейчас»: 30 дней, второй раз подряд 90, после третьего больше не предлагать
  afterSentDays: 120,       // после отправленного отзыва: 120 дней и не раньше следующей минорной версии
};
export const COPY = {
  prompt_usage: 'Как тебе KipClub?',
  prompt_update: 'Мы обновили KipClub. Как тебе новая версия?',
  prompt_error: 'Похоже, что-то пошло не так. Расскажешь, что случилось?',
  high: 'Спасибо! Хочешь рассказать, что нравится или чего не хватает?',
  low: 'Жаль. Расскажи, что мешает, мы поправим.',
  write: 'Написать', no: 'Не надо', later: 'Не сейчас',
};
export const FACES = [['1', '😞', 'очень плохо'], ['2', '🙁', 'плохо'], ['3', '😐', 'нормально'], ['4', '🙂', 'хорошо'], ['5', '😍', 'отлично']];
export const minorOf = v => String(v || '').match(/^v?(\d+\.\d+)/)?.[1] || '';
const dayKey = ts => new Date(ts + 3 * 3600e3).toISOString().slice(0, 10); // день по Москве

export function emptyState(now) {
  return { firstRun: now, opens: 0, scheduleDays: [], calendarExports: 0, favAdds: 0, shows: [], dismissStreak: 0, snoozeUntil: 0,
    never: false, sentAt: 0, sentMinor: '', version: '', versionSince: 0, versionOpens: 0, updated: false, errorPending: false };
}
export function load(storage, now = Date.now()) {
  try { const raw = JSON.parse(storage.getItem(STATE_KEY) || 'null'); if (raw && typeof raw === 'object') return { ...emptyState(now), ...raw }; } catch { /* битое */ }
  return emptyState(now);
}
export function save(storage, state) { try { storage.setItem(STATE_KEY, JSON.stringify(state)); } catch { /* storage недоступен */ } return state; }

// --- сигналы ---
export function recordOpen(state, { now, version }) {
  const s = { ...state, opens: state.opens + 1 };
  if (version && version !== s.version) {
    s.updated = !!s.version; s.version = version; s.versionSince = now; s.versionOpens = 0;
  }
  s.versionOpens += 1;
  return s;
}
export function recordScheduleDay(state, now) {
  const key = dayKey(now);
  return state.scheduleDays.includes(key) ? state : { ...state, scheduleDays: [...state.scheduleDays, key].slice(-10) };
}
export const recordCalendar = state => ({ ...state, calendarExports: state.calendarExports + 1 });
export const recordFav = state => ({ ...state, favAdds: state.favAdds + 1 });
export const recordError = state => ({ ...state, errorPending: true });

// --- решения ---
export function blocked(state, ctx) {
  const { now, online = true, busy = false, admin = false, sinceLaunchMs = Infinity, page = 'home', iosSafari = false } = ctx;
  if (state.never) return 'never';
  if (admin) return 'admin';
  if (!online) return 'offline';
  if (busy) return 'busy';
  if (iosSafari) return 'ios_safari';
  if (page !== 'home' && page !== 'week' && page !== 'day') return 'page';
  if (state.opens < RULES.minOpens) return 'first_opens';
  if (sinceLaunchMs < RULES.minSinceLaunchMs) return 'just_launched';
  if (state.snoozeUntil > now) return 'snoozed';
  const shows = state.shows.filter(t => now - t < 365 * DAY);
  if (shows.some(t => now - t < RULES.gapDays * DAY)) return 'gap';
  if (shows.length >= RULES.perYear) return 'per_year';
  if (state.sentAt && now - state.sentAt < RULES.afterSentDays * DAY) return 'after_sent';
  if (state.sentAt && state.sentMinor && state.sentMinor === minorOf(state.version)) return 'same_minor';
  return null;
}
export function trigger(state, ctx) {
  const { now, whatsNewSeen = false } = ctx;
  if (state.errorPending) return 'prompt_error';
  if (state.updated && whatsNewSeen && now - state.versionSince >= RULES.updateAgeDays * DAY && state.versionOpens >= RULES.updateOpens) return 'prompt_update';
  if (state.scheduleDays.length >= RULES.usageDays && now - state.firstRun >= RULES.usageAgeDays * DAY) return 'prompt_usage';
  if (state.calendarExports >= RULES.calendarExports || state.favAdds >= RULES.favAdds) return 'prompt_usage';
  return null;
}
export function decide(state, ctx) { return blocked(state, ctx) ? null : trigger(state, ctx); }

// --- исходы ---
export function markShown(state, now, source) {
  return { ...state, shows: [...state.shows.filter(t => now - t < 365 * DAY), now], errorPending: source === 'prompt_error' ? false : state.errorPending };
}
export function snooze(state, now) {
  const streak = state.dismissStreak + 1;
  if (streak >= 3) return { ...state, dismissStreak: streak, never: true };
  return { ...state, dismissStreak: streak, snoozeUntil: now + RULES.snoozeDays[streak - 1] * DAY };
}
export const rated = state => ({ ...state, dismissStreak: 0, updated: false });
export function sent(state, now) { return { ...state, dismissStreak: 0, sentAt: now, sentMinor: minorOf(state.version), errorPending: false, updated: false }; }
export const typeForRating = rating => (Number(rating) >= 4 ? 'idea' : 'bug');
export const followUp = rating => (Number(rating) >= 4 ? COPY.high : COPY.low);
