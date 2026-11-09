import test from 'node:test';
import assert from 'node:assert/strict';
import { createScheduleFeed } from '../js/schedule-feed.js';
import { createWeekStore, validWeekRecord } from '../js/schedule-storage.js';
import { indexSchedule, indexScheduleAsync } from '../js/schedule-search-model.js';
const week = new Date(2026, 10, 9);
const event = { event_id: '1:2026-11-09', club_id: 1, date: '2026-11-09', start_time: '10:00', end_time: '11:00', club_name: 'Шахматы', leader_name: 'Иван', room_name: '201', category_name: 'Спорт', status: 'scheduled' };
const row = events => ({ schema: 1, savedAt: Date.now(), events });
function store(read = async () => null) { return { read, write: async () => {}, clear: async () => {} }; }
globalThis.window ||= { dispatchEvent() {} };
if (!globalThis.CustomEvent) globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init?.detail; } };
test('persistent weeks have a bounded age and schema; future/corrupt data rejected', () => {
  assert.equal(validWeekRecord(row([event])), true);
  assert.equal(validWeekRecord({ ...row([]), savedAt: Date.now() - 49 * 3600_000 }), false);
  assert.equal(validWeekRecord({ ...row([]), savedAt: Date.now() + 120_000 }), false);
  assert.equal(validWeekRecord({ ...row([]), schema: 2 }), false);
  assert.equal(validWeekRecord(row('private')), false);
});
test('cache-first hydration renders a saved week before any network', async () => {
  const feed = createScheduleFeed({ store: store(async () => row([event])) });
  assert.equal(feed.read(week), undefined);
  assert.equal((await feed.hydrate(week))[0].club_name, 'Шахматы');
  assert.equal(feed.read(week).length, 1);
});
test('late disk hydration cannot overwrite a newer network week', async () => {
  let done;
  const feed = createScheduleFeed({ store: store(() => new Promise(resolve => { done = resolve; })) });
  const hydration = feed.hydrate(week);
  globalThis.fetch = async () => Response.json([{ ...event, club_name: 'Актуальные шахматы' }]);
  await feed.fetchWeek(week);
  done(row([event])); await hydration;
  assert.equal(feed.read(week)[0].club_name, 'Актуальные шахматы');
});
test('invalidated disk work cannot repopulate the cache', async () => {
  let done;
  const feed = createScheduleFeed({ store: store(() => new Promise(resolve => { done = resolve; })) });
  const hydration = feed.hydrate(week); feed.invalidate(); done(row([event])); await hydration;
  assert.equal(feed.read(week), undefined);
});
test('cancelling prefetch aborts the request and does not start the next neighbour', async () => {
  let calls = 0, aborted = 0;
  globalThis.fetch = (path, options) => new Promise((resolve, reject) => {
    calls++; options.signal.addEventListener('abort', () => { aborted++; reject(new DOMException('cancelled', 'AbortError')); });
  });
  const feed = createScheduleFeed({ store: store() });
  const request = feed.prefetch(week, () => true, () => {});
  feed.cancelPrefetch(); await request;
  assert.equal(calls, 1); assert.equal(aborted, 1);
});
test('native week store is scoped by backend origin and never writes browser storage', async () => {
  const before = globalThis.window;
  const calls = [];
  globalThis.window = { AppServer: { get: () => 'https://club.kipfin.ru' }, Capacitor: {
    isNativePlatform: () => true, Plugins: { ItcNative: {
      readWeek: async options => { calls.push(options); return row([event]); },
      writeWeek: async options => calls.push(options), clearWeeks: async options => calls.push(options),
    } },
  } };
  try {
    const cache = createWeekStore(); assert.equal((await cache.read('2026-11-09')).events.length, 1);
    await cache.write('2026-11-09', [event]); await cache.clear();
    assert.equal(calls.length, 3); assert.ok(calls.every(call => call.origin === 'https://club.kipfin.ru'));
  } finally { globalThis.window = before; }
});
test('chunked idle index preserves ranking and yields between batches', async () => {
  const events = Array.from({ length: 12 }, (_, i) => ({ ...event, event_id: String(i), club_name: 'Шахматы ' + i }));
  let yields = 0;
  const asyncIndex = await indexScheduleAsync(events, { chunkSize: 3, yieldTask: async () => { yields++; } });
  assert.equal(yields, 3);
  assert.deepEqual(asyncIndex('if[vfns').map(hit => hit.event.event_id), indexSchedule(events)('if[vfns').map(hit => hit.event.event_id));
  const abort = new AbortController(); abort.abort();
  await assert.rejects(indexScheduleAsync(events, { signal: abort.signal }), { name: 'AbortError' });
});
