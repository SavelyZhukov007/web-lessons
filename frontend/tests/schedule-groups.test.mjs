import test from 'node:test';
import assert from 'node:assert/strict';
import { eventGroups } from '../js/schedule-dates.js';

const event = (id, start_time, end_time) => ({ event_id: id, start_time, end_time });

test('частично пересекающиеся занятия попадают в одну группу без потери записей', () => {
  const groups = eventGroups([event('c', '11:20', '12:00'), event('a', '10:00', '11:00'), event('b', '10:50', '11:30')]);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].events.map(x => x.event_id), ['a', 'b', 'c']);
  assert.deepEqual([groups[0].start, groups[0].end], [600, 720]);
});

test('занятия встык остаются отдельными', () => {
  const groups = eventGroups([event('a', '14:00', '16:00'), event('b', '16:00', '17:20')]);
  assert.equal(groups.length, 2);
});
