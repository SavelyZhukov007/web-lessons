import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../shim/native-features.js', import.meta.url), 'utf8');
function app(initial = {}) {
  const data = new Map(Object.entries(initial));
  const storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key), key: index => [...data.keys()][index], get length() { return data.size; } };
  let online = true;
  const window = { ItcPwa: true, localStorage: storage, addEventListener() {}, fetch: async () => {
    if (!online) throw new Error('offline');
    return Response.json({ value: 'data' });
  } };
  const document = { readyState: 'loading', querySelector: () => ({}), getElementById: () => ({ remove() {} }),
    addEventListener() {}, documentElement: { classList: { toggle() {} } } };
  vm.runInNewContext(source, { window, document, navigator: { onLine: true }, URL, Response, Headers,
    location: { href: 'https://clubs.test/', pathname: '/' } });
  return { window, data, offline() { online = false; } };
}
test('admin and push responses are never stored or replayed offline', async () => {
  const state = app({ 'itc.cache:/api/admin/status': JSON.stringify({ t: Date.now(), b: { secret: 'old user' } }) });
  assert.equal(state.data.has('itc.cache:/api/admin/status'), false);
  for (const path of ['/api/admin/status', '/api/push/status']) {
    await state.window.fetch(path);
    assert.equal(state.data.has('itc.cache:' + path), false);
  }
  state.offline();
  await assert.rejects(state.window.fetch('/api/push/status'), /offline/);
});
test('public offline copy includes its original timestamp and an explicit marker', async () => {
  const state = app();
  await state.window.fetch('/api/clubs');
  state.offline();
  const response = await state.window.fetch('/api/clubs');
  assert.equal(response.headers.get('X-Clubs-Offline'), '1');
  assert.ok(Date.parse(response.headers.get('X-Clubs-Cached-At')));
  assert.equal((await response.json()).value, 'data');
});
