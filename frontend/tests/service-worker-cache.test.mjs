import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../sw.js', import.meta.url), 'utf8');
function worker() {
  const listeners = new Map(), stores = new Map();
  const cache = name => {
    if (!stores.has(name)) stores.set(name, new Map());
    const entries = stores.get(name);
    return {
      async put(request, response) { entries.set(request.url || request, response.clone()); },
      async match(request) { return entries.get(request.url || request)?.clone(); },
      async keys() { return [...entries.keys()].map(url => new Request(url)); },
      async delete(request) { return entries.delete(request.url || request); },
    };
  };
  let online = true;
  const context = { self: { location: { origin: 'https://clubs.test' }, addEventListener(name, cb) { listeners.set(name, cb); } },
    caches: { open: async name => cache(name) }, Headers, Response, Request, URL,
    fetch: async () => { if (!online) throw new Error('offline'); return Response.json([{ name: 'Кружок' }]); } };
  vm.runInNewContext(source, context);
  return { cache, offline() { online = false; }, async get(path) {
    let promise;
    listeners.get('fetch')({ request: new Request(`https://clubs.test${path}`), respondWith(p) { promise = p; } });
    return promise;
  } };
}
test('offline API response identifies the saved copy and its time', async () => {
  const sw = worker();
  assert.equal((await sw.get('/api/clubs')).status, 200);
  sw.offline();
  const response = await sw.get('/api/clubs');
  assert.equal(response.headers.get('X-Clubs-Offline'), '1');
  assert.ok(Date.parse(response.headers.get('X-Clubs-Cached-At')));
  assert.equal((await response.json())[0].name, 'Кружок');
});
test('expired API cache is rejected rather than presented as current', async () => {
  const sw = worker();
  await sw.cache('clubs-api-dev').put(new Request('https://clubs.test/api/clubs'), Response.json([], {
    headers: { 'X-Clubs-Cached-At': new Date(Date.now() - 49 * 3600e3).toISOString() },
  }));
  sw.offline();
  await assert.rejects(sw.get('/api/clubs'), /offline/);
});
test('private attendance and teacher responses never enter the cache', async () => {
  const sw = worker();
  assert.equal(await sw.get('/api/teacher/me'), undefined);
  assert.equal(await sw.get('/api/attendance/mine'), undefined);
});
