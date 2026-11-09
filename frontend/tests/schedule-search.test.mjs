import test from 'node:test';
import assert from 'node:assert/strict';
import { indexSchedule } from '../js/schedule-search-model.js';
import { dateKey, parseDate } from '../js/schedule-dates.js';
import { dayMarkers, stepStudyDay } from '../js/schedule-navigation.js';
import { eventUrl } from '../js/schedule-share.js';

const base = { date: '2026-11-10', leader_name: 'Иванов', room_name: '205', category_name: 'Наука', start_time: '13:00' };
const robotics = { ...base, event_id: '1', club_name: 'Робототехника', status: 'scheduled' };
const openDay = { ...base, event_id: '2', club_name: 'День открытых дверей', room_name: '2050', status: 'scheduled' };
const find = indexSchedule([robotics, openDay]);

test('поиск понимает опечатки, раскладку и транслит, сохраняет точные номера', () => {
  for (const query of ['робототехнка', 'hj,jnjnt[ybrf', 'robototekhnika', 'Робото 205']) {
    assert.equal(find(query)[0].event, robotics);
  }
  assert.equal(find('den')[0].event, openDay);
  assert.deepEqual(find('205').map(hit => hit.event), [robotics]);
  assert.deepEqual(find('робототехника', '2026-11-14'), []);
});

test('шаг через выходной и точки у обоих слотов переноса', () => {
  assert.equal(dateKey(stepStudyDay(parseDate('2026-11-14'), 1)), '2026-11-16');
  assert.equal(dateKey(stepStudyDay(parseDate('2026-11-16'), -1)), '2026-11-14');
  const markers = dayMarkers([{ ...robotics, status: 'moved', original_date: '2026-11-09' },
    { ...openDay, status: 'cancelled' }]);
  assert.deepEqual([...markers.get('2026-11-09')], ['moved']);
  assert.deepEqual([...markers.get('2026-11-10')], ['scheduled', 'moved', 'cancelled']);
});

test('ссылка содержит день, неделю и идентификатор занятия', () => {
  assert.equal(eventUrl({ ...robotics, event_id: '11:2026-11-10' }, 'https://club.example'),
    'https://club.example/?week=2026-11-09&day=2026-11-10&event=11%3A2026-11-10');
});
