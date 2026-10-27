import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../shim/app-student.js', import.meta.url), 'utf8');

test('Android saves the administrator role before the login request resolves', async () => {
  const values = new Map();
  const storage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
  let finishBody;
  const body = new Promise(resolve => { finishBody = resolve; });
  const response = { ok: true, clone: () => ({ json: () => body }) };
  const window = { localStorage: storage, fetch: async () => response, addEventListener() {}, dispatchEvent() {} };
  const document = { readyState: 'loading', addEventListener() {}, documentElement: {} };
  vm.runInNewContext(source, { window, document, URLSearchParams, CustomEvent: class {} });
  let completed = false;
  const request = window.fetch('/api/admin/login').then(result => { completed = true; return result; });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(completed, false);
  finishBody({ access_token: 'test', refresh_expires_in: 60, admin: { login: 'qa' } });
  assert.equal(await request, response);
  assert.equal(JSON.parse(values.get('itc.session')).role, 'admin');
});
