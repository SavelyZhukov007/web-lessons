import test from 'node:test';
import assert from 'node:assert/strict';
import { roomLabel, eventRoom, calendarDate } from '../js/public-display.js';
import { migrateLegacyState } from '../js/legacy-state.js';

test('same room number in different buildings remains distinguishable', () => {
  assert.equal(roomLabel({ name: '101', building: 'Второй корпус' }), '101 · Второй корпус');
  assert.equal(eventRoom({ room_id: 2, room_name: '101' }, new Map([[2, { building: 'Второй корпус' }]])), '101 · Второй корпус');
  assert.equal(roomLabel(null, 'Название не загрузилось'), 'Название не загрузилось');
});
test('calendar dates reject impossible days and do not shift to another timezone day', () => {
  assert.match(calendarDate('2027-01-05'), /5 января 2027/);
  assert.equal(calendarDate('2027-02-30'), '2027-02-30');
});
test('legacy migration preserves follows, notification choices and current admin tokens', () => {
  for (const role of ['student', 'teacher']) {
    const values = new Map([['itc.session', JSON.stringify({ role })], ['itc.role', role], ['itc.vault.v1', 'old encrypted profile'],
      ['itc.checkinQueue', '[1]'], ['itc.follows', '[2,3]'], ['itc.pwa.announcements', '0'], ['clubs.adminToken', 'unchanged']]);
    const storage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
    const deleted = [];
    migrateLegacyState(storage, { deleteDatabase: key => deleted.push(key) });
    assert.equal(JSON.parse(values.get('itc.session')).role, 'guest');
    assert.equal(values.has('itc.vault.v1'), false);
    assert.equal(values.has('itc.checkinQueue'), false);
    assert.equal(values.get('itc.follows'), '[2,3]');
    assert.equal(values.get('itc.pwa.announcements'), '0');
    assert.equal(values.get('clubs.adminToken'), 'unchanged');
    assert.deepEqual(deleted, ['itc-secure']);
    migrateLegacyState(storage, { deleteDatabase: key => deleted.push(key) });
    assert.equal(deleted.length, 1);
  }
});
test('blocked storage does not stop the application', () => {
  assert.doesNotThrow(() => migrateLegacyState({ getItem() { throw Error('blocked'); } }));
});

test('a stale legacy role cannot replace an active admin session', () => {
  const values = new Map([['itc.session', '{"role":"admin","name":"Admin"}'], ['itc.role', 'student']]);
  migrateLegacyState({ getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) });
  assert.equal(JSON.parse(values.get('itc.session')).role, 'admin');
});
