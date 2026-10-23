// Не требует npm-пакетов: node --test frontend/tests/schedule-dates.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseDate, dateKey, addDays, monday, moscowToday, eventLanes } from '../js/schedule-dates.js';

const event = (id, start, end) => ({ event_id: id, start_time: start, end_time: end });

test('Календарные даты: високосный год и невозможные дни', () => {
  assert.equal(dateKey(parseDate('2028-02-29')), '2028-02-29');
  for (const value of ['2026-02-29', '2026-04-31', '2026-13-01', '2026-10-00', '26-10-01', '', '1899-12-31']) {
    assert.equal(parseDate(value), null, value);
  }
});

test('Границы недели, месяца и года без преобразования дня в UTC', () => {
  assert.equal(dateKey(monday(parseDate('2027-01-01'))), '2026-12-28');
  assert.equal(dateKey(monday(parseDate('2026-10-25'))), '2026-10-19');
  assert.equal(dateKey(addDays(parseDate('2026-12-31'), 1)), '2027-01-01');
  assert.equal(dateKey(addDays(parseDate('2028-03-01'), -1)), '2028-02-29');
});

test('Календарная арифметика при переводе часов', () => {
  const previous = process.env.TZ;
  process.env.TZ = 'America/New_York';
  try {
    assert.equal(dateKey(addDays(parseDate('2026-03-07'), 2)), '2026-03-09');
    assert.equal(dateKey(addDays(parseDate('2026-10-31'), 2)), '2026-11-02');
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test('Сегодня определяется по Москве, даже когда в UTC ещё предыдущий день', () => {
  const RealDate = globalThis.Date;
  globalThis.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : ['2026-10-20T22:30:00Z'])); }
  };
  try { assert.equal(dateKey(moscowToday()), '2026-10-21'); }
  finally { globalThis.Date = RealDate; }
});

test('Соседние занятия не занимают параллельные полосы', () => {
  const layout = eventLanes([event('b', '11:00', '12:00'), event('a', '10:00', '11:00')]);
  assert.deepEqual(layout.map(({ event, lane, lanes }) => [event.event_id, lane, lanes]), [['a', 0, 1], ['b', 0, 1]]);
});

test('Вложенные и одновременные интервалы получают непересекающиеся полосы', () => {
  const input = [event('a', '10:00', '14:00'), event('b', '10:00', '11:00'), event('c', '10:30', '12:00'), event('d', '11:00', '13:00'), event('e', '15:00', '16:00')];
  const originalOrder = input.map(item => item.event_id);
  const layout = eventLanes(input);
  assert.deepEqual(input.map(item => item.event_id), originalOrder, 'Не изменяет входной массив');
  for (const a of layout) for (const b of layout) {
    if (a === b) continue;
    const overlap = a.event.start_time < b.event.end_time && b.event.start_time < a.event.end_time;
    if (overlap) assert.notEqual(a.lane, b.lane);
  }
  assert.equal(layout.find(item => item.event.event_id === 'a').lanes, 3);
  assert.equal(layout.find(item => item.event.event_id === 'e').lanes, 1);
  assert.deepEqual(eventLanes([]), []);
});
