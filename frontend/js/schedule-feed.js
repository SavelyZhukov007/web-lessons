import { getSchedule } from './api.js';
import { addDays, dateKey, parseDate, minutes } from './schedule-dates.js';
import { weekInRange } from './schedule-navigation.js';

const FRESH_MS = 60_000;
const LIMIT = 12;
const time = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const statuses = new Set(['scheduled', 'moved', 'cancelled']);

function validate(data, week) {
  if (!Array.isArray(data) || data.some(event => !event || typeof event.event_id !== 'string'
    || !Number.isInteger(event.club_id) || event.club_id <= 0 || !parseDate(event.date)
    || !time.test(event.start_time) || !time.test(event.end_time)
    || minutes(event.start_time) >= minutes(event.end_time)
    || !['club_name', 'leader_name', 'room_name', 'category_name'].every(key => typeof event[key] === 'string')
    || !statuses.has(event.status))) {
    throw new Error('Сервер вернул расписание в неожиданном формате. Попробуй обновить данные.');
  }
  const first = dateKey(week), last = dateKey(addDays(week, 5));
  return data.filter(event => (event.date >= first && event.date <= last)
    || (event.status === 'moved' && event.original_date >= first && event.original_date <= last));
}

export function createScheduleFeed() {
  const cache = new Map();
  const inflight = new Map();
  let generation = 0;

  function fetchWeek(week, { refresh = false } = {}) {
    const key = dateKey(week);
    const old = cache.get(key);
    if (!refresh && old && Date.now() - old.time < FRESH_MS) return Promise.resolve(old.events);
    if (inflight.has(key)) return inflight.get(key);
    const started = generation;
    const request = getSchedule(key, {}, { itcUnfilteredSchedule: true }).then(data => {
      const checked = validate(data, week);
      const events = old && JSON.stringify(old.events) === JSON.stringify(checked) ? old.events : checked;
      if (started === generation) {
        cache.delete(key);
        cache.set(key, { time: Date.now(), events });
        if (cache.size > LIMIT) cache.delete(cache.keys().next().value);
      }
      return events;
    }).finally(() => { if (inflight.get(key) === request) inflight.delete(key); });
    inflight.set(key, request);
    return request;
  }

  return {
    read: week => cache.get(dateKey(week))?.events,
    fetchWeek,
    async prefetch(week, isCurrent, onReady) {
      for (const offset of [7, -7]) {
        if (!isCurrent()) break;
        const target = addDays(week, offset);
        if (!weekInRange(target)) continue;
        try { await fetchWeek(target); if (isCurrent()) onReady(); } catch { /* active week remains usable */ }
      }
    },
    invalidate() {
      generation++;
      inflight.clear();
      for (const entry of cache.values()) entry.time = 0;
    },
  };
}

export function filteredEvents(events, filters, follows) {
  const category = Number(filters.category_id.value);
  const leader = Number(filters.leader_id.value);
  const room = Number(filters.room_id.value);
  if (!category && !leader && !room && !follows) return events;
  return events.filter(event =>
    (!category || event.category_id === category)
    && (!leader || (event.leader_ids?.length ? event.leader_ids : [event.leader_id]).includes(leader))
    && (!room || (event.room_ids?.length ? event.room_ids : [event.room_id]).includes(room))
    && (!follows || follows.has(event.club_id)));
}
