import test from 'node:test';
import assert from 'node:assert/strict';
import { sessions } from '../js/admin/api.js';

function conflict(token) {
  return new Response(JSON.stringify({ detail: { message: 'Пересечение', confirmation_token: token,
    conflicts: [{ club_name: 'Кружок', date: '2026-11-03', start_time: '15:50', end_time: '17:20', reasons: ['room', 'leader'] }] } }),
  { status: 409, headers: { 'Content-Type': 'application/json' } });
}

test('confirmation retries with the token after showing room and leader', async () => {
  const oldWindow = globalThis.window, oldFetch = globalThis.fetch;
  const calls = [], prompts = [];
  globalThis.window = { confirm: message => { prompts.push(message); return true; } };
  globalThis.fetch = async (_path, options) => {
    calls.push(options);
    return calls.length === 1 ? conflict('first') : new Response('{"id":1}', { status: 201 });
  };
  try {
    assert.deepEqual(await sessions.create({ weekday: 2 }), { id: 1 });
    assert.match(prompts[0], /общая аудитория/);
    assert.match(prompts[0], /общий руководитель/);
    assert.equal(calls[1].headers['X-Confirmed-Conflicts'], 'first');
  } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch; }
});

test('declining leaves the request unsaved and never retries', async () => {
  const oldWindow = globalThis.window, oldFetch = globalThis.fetch;
  let calls = 0;
  globalThis.window = { confirm: () => false };
  globalThis.fetch = async () => { calls++; return conflict('first'); };
  try {
    await assert.rejects(sessions.create({ weekday: 2 }), { status: 409 });
    assert.equal(calls, 1);
  } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch; }
});
