import { getSchedule } from './api.js';
import { addDays, dateKey, parseDate, minutes } from './schedule-dates.js';
import { weekInRange } from './schedule-navigation.js';
import { createWeekStore, validWeekRecord } from './schedule-storage.js';

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

export function createScheduleFeed({ store = createWeekStore() } = {}) {
  const cache = new Map(), inflight = new Map();
  let generation = 0, prefetchEpoch = 0;
  function remember(key, events, time, source = 'network') {
    cache.delete(key); cache.set(key, { time, events, source });
    if (cache.size > LIMIT) cache.delete(cache.keys().next().value);
  }
  async function hydrate(week) {
    const key = dateKey(week), started = generation;
    if (cache.has(key)) return cache.get(key).events;
    const row = await store.read(key);
    if (started !== generation) return;
    if (cache.has(key)) return cache.get(key).events; // never replace a faster network response with old disk data
    if (!validWeekRecord(row)) return;
    try { const events = validate(row.events, week); remember(key, events, row.savedAt, 'cache'); if (row.migrated) void store.write(key, events, row.savedAt); return events; }
    catch { return; }
  }
  function fetchWeek(week, { refresh = false, prefetch = false } = {}) {
    const key = dateKey(week), old = cache.get(key);
    if (!refresh && old && Date.now() - old.time < FRESH_MS) return Promise.resolve(old.events);
    if (inflight.has(key)) {
      const entry = inflight.get(key); if (!prefetch) entry.prefetch = false;
      return entry.promise;
    }
    const started = generation, controller = new AbortController();
    const entry = { controller, prefetch }; let meta;
    entry.promise = getSchedule(key, {}, { itcUnfilteredSchedule: true, itcPersistentWeekCache: true,
      signal: controller.signal, onCacheState: value => { meta = value; } }).then(data => {
      const checked = validate(data, week), current = cache.get(key);
      const events = current && JSON.stringify(current.events) === JSON.stringify(checked) ? current.events : checked;
      if (started === generation && !controller.signal.aborted) {
        const savedAt = Date.parse(meta?.savedAt) || Date.now();
        remember(key, events, savedAt, meta?.offline ? 'cache' : 'network'); void store.write(key, events, savedAt);
      }
      return events;
    }).finally(() => { if (inflight.get(key) === entry) inflight.delete(key); });
    inflight.set(key, entry);
    return entry.promise;
  }
  function cancelPrefetch(except) {
    prefetchEpoch++;
    for (const [key, entry] of inflight) if (entry.prefetch && key !== except) { entry.controller.abort(); inflight.delete(key); }
  }
  return {
    read: week => cache.get(dateKey(week))?.events,
    info: week => cache.get(dateKey(week)),
    hydrate, fetchWeek, cancelPrefetch,
    activate(week) { cancelPrefetch(dateKey(week)); },
    async prefetch(week, isCurrent, onReady) {
      const connection = globalThis.navigator?.connection;
      if (globalThis.window?.ItcPerformance?.powerSave || connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || '')) return;
      const epoch = prefetchEpoch;
      for (const offset of [7, -7]) {
        if (!isCurrent() || epoch !== prefetchEpoch || globalThis.document?.hidden) break;
        const target = addDays(week, offset);
        if (!weekInRange(target)) continue;
        try { await fetchWeek(target, { prefetch: true }); if (isCurrent()) onReady(); } catch { /* active week remains usable */ }
      }
    },
    invalidate({ persisted = false } = {}) {
      generation++; prefetchEpoch++;
      for (const entry of inflight.values()) entry.controller.abort();
      inflight.clear();
      for (const entry of cache.values()) entry.time = 0;
      if (persisted) void store.clear();
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
