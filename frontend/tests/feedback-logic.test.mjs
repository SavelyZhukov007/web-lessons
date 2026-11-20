import test from 'node:test';
import assert from 'node:assert/strict';
import { validate, buildFormData, DESC_MAX } from '../js/feedback-logic.js';

const ok = { type: 'bug', description: 'Не грузится расписание', contact: '', files: [] };

test('validation messages', () => {
  assert.deepEqual(validate(ok), {});
  assert.ok(validate({ ...ok, description: 'коротко' }).description);
  assert.ok(validate({ ...ok, description: 'x'.repeat(DESC_MAX + 1) }).description);
  assert.ok(validate({ ...ok, type: 'x' }).type);
  assert.ok(validate({ ...ok, contact: 'not ok!' }).contact);
  assert.deepEqual(validate({ ...ok, contact: '@tester' }), {});
  assert.ok(validate({ ...ok, files: Array(6).fill({ type: 'image/png', size: 1 }) }).files);
  assert.ok(validate({ ...ok, files: [{ type: 'image/gif', size: 1 }] }).files);
  assert.ok(validate({ ...ok, files: [{ type: 'image/png', size: 6 * 1024 * 1024 }] }).files);
});

test('logs and device data are always attached', () => {
  const fd = buildFormData({ ...ok, description: '  текст текст  ', info: { version: 'v1.7.829ibW' }, logs: [{ level: 'error', msg: 'x' }],
    files: [{ file: new Blob(['a']), type: 'image/png' }, { file: new Blob(['b']), type: 'image/jpeg' }] });
  assert.equal(fd.get('description'), 'текст текст');
  assert.deepEqual(JSON.parse(fd.get('logs')), [{ level: 'error', msg: 'x' }]);
  assert.equal(JSON.parse(fd.get('meta')).version, 'v1.7.829ibW');
  assert.deepEqual(fd.getAll('screenshots').map(f => f.name), ['01.png', '02.jpeg']);
  assert.equal(buildFormData({ ...ok }).get('logs'), '[]', 'empty buffer still sends logs');
});

test('rating and source fields, texts in «ты» without long dashes', async () => {
  const { SOURCES } = await import('../js/feedback-logic.js');
  const fd = buildFormData({ ...ok, rating: 4, source: 'prompt_update' });
  assert.equal(fd.get('rating'), '4'); assert.equal(fd.get('source'), 'prompt_update');
  const none = buildFormData({ ...ok, rating: 9, source: '<x>' });
  assert.equal(none.get('rating'), null); assert.equal(none.get('source'), 'settings');
  assert.deepEqual(SOURCES, ['settings', 'prompt_usage', 'prompt_update', 'prompt_error', 'whats_new', 'shake', 'offline', 'error']);
  const messages = Object.values({ ...validate({ ...ok, type: 'x', description: 'a' }), ...validate({ ...ok, files: [{ type: 'image/png', size: 6e6 }] }) });
  assert.deepEqual(messages, ['Выбери тип сообщения', 'Напиши чуть подробнее, хотя бы 10 символов', 'Один скриншот до 5 МБ']);
  for (const m of messages) assert.ok(!m.includes('—') && !/Выберите|Опишите/.test(m));
});
