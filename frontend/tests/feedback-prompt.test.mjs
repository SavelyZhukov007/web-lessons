import test from 'node:test';
import assert from 'node:assert/strict';
import * as P from '../js/feedback-prompt-logic.js';

const DAY = P.DAY, T0 = Date.parse('2026-11-01T09:00:00Z');
const ctx = (now, extra = {}) => ({ now, online: true, busy: false, admin: false, sinceLaunchMs: 60e3, page: 'home', iosSafari: false, whatsNewSeen: false, ...extra });
function mature(now = T0 + 8 * DAY) { // 5 дней с расписанием, 8 дней с первого запуска, 6 открытий
  let s = P.emptyState(T0);
  for (let i = 0; i < 6; i++) s = P.recordOpen(s, { now: T0 + i * DAY, version: '1.9.024' });
  for (let i = 0; i < 5; i++) s = P.recordScheduleDay(s, T0 + i * DAY);
  return { s, now };
}

test('usage trigger needs 5 schedule days and 7 days since first run', () => {
  const { s, now } = mature();
  assert.equal(P.decide(s, ctx(now)), 'prompt_usage');
  assert.equal(P.decide(s, ctx(T0 + 6 * DAY)), null, 'раньше 7 дней');
  const fewDays = { ...s, scheduleDays: s.scheduleDays.slice(0, 4) };
  assert.equal(P.decide(fewDays, ctx(now)), null);
  assert.equal(P.recordScheduleDay(s, T0 + 4 * DAY + 3600e3).scheduleDays.length, 5, 'тот же день не считается дважды');
});

test('success moments: second calendar export or 3 favourites', () => {
  let s = P.emptyState(T0); for (let i = 0; i < 4; i++) s = P.recordOpen(s, { now: T0, version: '1.9.024' });
  assert.equal(P.decide(P.recordCalendar(s), ctx(T0 + DAY)), null);
  assert.equal(P.decide(P.recordCalendar(P.recordCalendar(s)), ctx(T0 + DAY)), 'prompt_usage');
  assert.equal(P.decide(P.recordFav(P.recordFav(P.recordFav(s))), ctx(T0 + DAY)), 'prompt_usage');
});

test('update trigger: 2 days after update, 2 opens on new version, «Что нового» seen', () => {
  let { s } = mature(); s = { ...s, scheduleDays: [] };
  s = P.recordOpen(s, { now: T0 + 10 * DAY, version: '1.9.025' });
  assert.equal(s.updated, true);
  assert.equal(P.decide(s, ctx(T0 + 13 * DAY, { whatsNewSeen: true })), null, 'одно открытие на новой версии');
  s = P.recordOpen(s, { now: T0 + 11 * DAY, version: '1.9.025' });
  assert.equal(P.decide(s, ctx(T0 + 11.5 * DAY, { whatsNewSeen: true })), null, 'меньше 2 дней');
  assert.equal(P.decide(s, ctx(T0 + 13 * DAY, { whatsNewSeen: false })), null, '«Что нового» не видел');
  assert.equal(P.decide(s, ctx(T0 + 13 * DAY, { whatsNewSeen: true })), 'prompt_update');
});

test('error trigger wins and is cleared when shown', () => {
  const { s, now } = mature();
  const err = P.recordError(s);
  assert.equal(P.decide(err, ctx(now)), 'prompt_error');
  assert.equal(P.markShown(err, now, 'prompt_error').errorPending, false);
});

test('never: first 3 opens, offline, busy, admin, first 10 s, install page, iOS Safari', () => {
  const { s, now } = mature();
  let young = P.emptyState(T0); for (let i = 0; i < 3; i++) young = P.recordOpen(young, { now: T0, version: '1' });
  young = P.recordCalendar(P.recordCalendar(young));
  assert.equal(P.blocked(young, ctx(now)), 'first_opens');
  assert.equal(P.blocked(s, ctx(now, { online: false })), 'offline');
  assert.equal(P.blocked(s, ctx(now, { busy: true })), 'busy');
  assert.equal(P.blocked(s, ctx(now, { admin: true })), 'admin');
  assert.equal(P.blocked(s, ctx(now, { sinceLaunchMs: 9e3 })), 'just_launched');
  assert.equal(P.blocked(s, ctx(now, { page: 'install' })), 'page');
  assert.equal(P.blocked(s, ctx(now, { iosSafari: true })), 'ios_safari');
});

test('frequency caps: once per 30 days, at most 4 per year', () => {
  let { s, now } = mature();
  s = P.rated(P.markShown(s, now, 'prompt_usage'));
  assert.equal(P.blocked(s, ctx(now + 29 * DAY)), 'gap');
  assert.equal(P.blocked(s, ctx(now + 31 * DAY)), null);
  for (const k of [1, 2, 3]) s = P.markShown(s, now + k * 31 * DAY, 'prompt_usage');
  assert.equal(P.blocked(s, ctx(now + 4 * 31 * DAY + DAY)), 'per_year');
  assert.equal(P.blocked(s, ctx(now + 366 * DAY + 31 * DAY)), null, 'старые показы уходят из годового окна');
});

test('snooze: 30 days, then 90 days in a row, third «Не сейчас» stops self prompts', () => {
  let { s, now } = mature();
  s = P.snooze(s, now); assert.equal(s.snoozeUntil, now + 30 * DAY); assert.equal(P.blocked(s, ctx(now + 29 * DAY)), 'snoozed');
  s = P.snooze(s, now + 31 * DAY); assert.equal(s.snoozeUntil, now + 121 * DAY);
  s = P.snooze(s, now + 122 * DAY); assert.equal(s.never, true); assert.equal(P.blocked(s, ctx(now + 500 * DAY)), 'never');
  let r = P.snooze(mature().s, now); r = P.rated(r); r = P.snooze(r, now + 40 * DAY); assert.equal(r.dismissStreak, 1, 'оценка сбрасывает серию отказов');
});

test('after a sent review: 120 days and not before next minor version', () => {
  let { s, now } = mature();
  s = P.sent(s, now);
  assert.equal(s.sentMinor, '1.9');
  assert.equal(P.blocked(s, ctx(now + 100 * DAY)), 'after_sent');
  assert.equal(P.blocked(s, ctx(now + 130 * DAY)), 'same_minor');
  s = P.recordOpen(s, { now: now + 125 * DAY, version: '1.10.001' });
  assert.equal(P.blocked(s, ctx(now + 130 * DAY)), null);
});

test('state round-trip, rating follow-ups and copy without long dashes', () => {
  const store = new Map(); const storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const { s } = mature(); P.save(storage, s); assert.deepEqual(P.load(storage), s);
  store.set(P.STATE_KEY, '{bad'); assert.equal(P.load(storage, 5).opens, 0);
  assert.equal(P.typeForRating('5'), 'idea'); assert.equal(P.typeForRating(2), 'bug');
  assert.equal(P.followUp(4), 'Спасибо! Хочешь рассказать, что нравится или чего не хватает?');
  assert.equal(P.followUp(1), 'Жаль. Расскажи, что мешает, мы поправим.');
  assert.equal(P.COPY.prompt_usage, 'Как тебе KipClub?');
  for (const text of Object.values(P.COPY)) assert.ok(!/[—–]/.test(text) && !/\bВы\b|ваш/i.test(text), text);
  assert.deepEqual(P.FACES.map(f => f[0]), ['1', '2', '3', '4', '5']);
});
