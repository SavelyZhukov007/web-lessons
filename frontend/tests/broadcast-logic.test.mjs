import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPayload, filterClubs, audienceLabel, formatMsk, reachText, deliveryText, newIdempotencyKey, TITLE_MAX, BODY_MAX } from '../js/admin/broadcast-logic.js';

const base = { title: ' Собрание ', body: ' В пятницу ', audience: 'all', key: 'k'.repeat(16) };

test('«Всем»: обрезаем пробелы, без кружков и занятий', () => {
  const { errors, payload } = buildPayload({ ...base, clubIds: [3], sessionIds: [7] });
  assert.deepEqual(errors, {});
  assert.deepEqual(payload, { title: 'Собрание', body: 'В пятницу', audience: 'all', idempotency_key: base.key });
});
test('обязательные поля и лимиты длины', () => {
  assert.deepEqual(Object.keys(buildPayload({ ...base, title: ' ', body: '' }).errors).sort(), ['body', 'title']);
  assert.ok(buildPayload({ ...base, title: 'x'.repeat(TITLE_MAX + 1) }).errors.title);
  assert.ok(buildPayload({ ...base, body: 'x'.repeat(BODY_MAX + 1) }).errors.body);
  assert.deepEqual(buildPayload({ ...base, title: 'x'.repeat(TITLE_MAX), body: 'y'.repeat(BODY_MAX) }).errors, {});
});
test('кружки: нужен хотя бы один; занятия только выбранных кружков', () => {
  assert.ok(buildPayload({ ...base, audience: 'clubs', clubIds: new Set() }).errors.audience);
  const sessionClub = new Map([[10, 2], [11, 5]]);
  const { payload } = buildPayload({ ...base, audience: 'clubs', clubIds: new Set([5, 2]), sessionIds: new Set([11, 10, 99]), sessionClub, url: '/club.html?id=2' });
  assert.deepEqual(payload.club_ids, [2, 5]);
  assert.deepEqual(payload.session_ids, [10, 11]);
  assert.equal(payload.url, '/club.html?id=2');
});
test('поиск кружков без учёта регистра и «ё»', () => {
  const clubs = [{ name: 'Шахматы' }, { name: 'Ёлочные игрушки' }, { name: 'Робототехника' }];
  assert.deepEqual(filterClubs(clubs, 'ЕЛОЧ').map(c => c.name), ['Ёлочные игрушки']);
  assert.equal(filterClubs(clubs, '  ').length, 3);
});
test('подпись аудитории', () => {
  assert.equal(audienceLabel({ audience: 'all' }), 'Всем');
  assert.equal(audienceLabel({ audience: 'clubs', club_names: ['A', 'B'] }), 'A, B');
  assert.equal(audienceLabel({ audience: 'clubs', club_names: ['A', 'B', 'C', 'D', 'E'] }), 'A, B, C и ещё 2');
});
test('время по Москве', () => {
  assert.equal(formatMsk('2026-10-25T17:15:00Z'), '25.10.2026, 20:15 МСК');
  assert.equal(formatMsk('2026-12-31T22:05:00Z'), '01.01.2027, 01:05 МСК');
  assert.equal(formatMsk('мусор'), '');
});
test('охват и итог доставки с правильными окончаниями', () => {
  assert.equal(reachText({ web: 1, apk: 3 }), 'Браузеры (Web Push): 1 подписка · Приложение Android: 3 устройства');
  assert.equal(reachText({ web: 11, apk: 0 }), 'Браузеры (Web Push): 11 подписок · Приложение Android: 0 устройств');
  assert.equal(deliveryText({ web_sent: 2, web_failed: 1, apk_targets: 21 }), 'Web Push: 2 отправлено, 1 с ошибкой · Android: 21 устройство');
});
test('ключ идемпотентности: 32 hex-символа, каждый раз новый', () => {
  const a = newIdempotencyKey(), b = newIdempotencyKey();
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.notEqual(a, b);
});
