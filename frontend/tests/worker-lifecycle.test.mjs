import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../sw.js', import.meta.url), 'utf8');
function setup(prefs, active = true) {
  const listeners = new Map(), stores = new Map(), calls = [];
  let activated = 0, subscribed = 0;
  const storageKey = 'https://clubs.test/__clubs/push-preferences';
  const cache = name => {
    if (!stores.has(name)) stores.set(name, new Map());
    const entries = stores.get(name);
    return {
      match: async r => entries.get(r.url || r)?.clone(),
      put: async (r, v) => { entries.set(r.url || r, v.clone()); },
      keys: async () => [...entries.keys()].map(url => new Request(url)),
      delete: async r => entries.delete(r.url || r),
      add: async () => {},
    };
  };
  class BrowserRequest extends Request {
    constructor(input, options) { super(typeof input === 'string' ? new URL(input, 'https://clubs.test') : input, options); }
  }
  const context = { URL, Request: BrowserRequest, Response, Headers, Uint8Array, atob, Date,
    caches: { open: async name => cache(name) },
    self: { location: { origin: 'https://clubs.test' },
      skipWaiting: async () => { activated++; },
      registration: { active: active ? {} : null, pushManager: { subscribe: async () => { subscribed++; return { toJSON: () => ({ endpoint: 'https://push.test/new', keys: { auth: 'a', p256dh: 'b' } }) }; } } },
      addEventListener: (name, cb) => listeners.set(name, cb) },
    fetch: async (input, options) => {
      const path = typeof input === 'string' ? input : input.url;
      const body = options?.body ? JSON.parse(options.body) : null;
      calls.push({ path, body });
      if (path.endsWith('/vapid-public-key')) return Response.json({ publicKey: 'AQID' });
      if (path.endsWith('/status')) { if (!prefs) return new Response('unavailable', { status: 503 }); return Response.json(prefs); }
      return Response.json({});
    },
  };
  vm.runInNewContext(source, context);
  if (prefs) cache('clubs-push-preferences').put(storageKey, Response.json({ endpoint: 'https://push.test/old', ...prefs }));
  return { calls, counts: () => ({ activated, subscribed }), async fire(name, extra = {}) {
    let done;
    listeners.get(name)({ ...extra, waitUntil: p => { done = p; } });
    await done;
  }, get(path) {
    let done;
    listeners.get('fetch')({ request: new Request('https://clubs.test' + path), respondWith: p => { done = p; } });
    return done;
  } };
}

test('rotated subscription keeps selected clubs and disabled announcements', async () => {
  const sw = setup({ all: false, club_ids: [2, 7], announcements: false });
  await sw.fire('pushsubscriptionchange', { oldSubscription: { endpoint: 'https://push.test/old' } });
  assert.deepEqual(sw.calls.filter(c => c.path.endsWith('/subscribe')).map(c => c.body.club_id), [2, 7]);
  assert.equal(sw.calls.find(c => c.path.endsWith('/preferences')).body.announcements, false);
  assert.equal(sw.calls.some(c => c.path.endsWith('/unsubscribe') && c.body.endpoint.endsWith('/old')), true);
});
test('missing saved consent never becomes a subscription to all clubs', async () => {
  const sw = setup(null);
  await sw.fire('pushsubscriptionchange', { oldSubscription: { endpoint: 'https://push.test/old' } });
  assert.equal(sw.counts().subscribed, 0);
  assert.equal(sw.calls.some(c => c.path.endsWith('/subscribe')), false);
});
test('updates wait for a page activation message while first installation can activate', async () => {
  const update = setup(null);
  await update.fire('install');
  assert.equal(update.counts().activated, 0);
  await update.fire('message', { data: { type: 'clubs:activate' } });
  assert.equal(update.counts().activated, 1);
  const first = setup(null, false);
  await first.fire('install');
  assert.equal(first.counts().activated, 1);
});
test('version metadata never falls back to cached old build information', () => {
  const sw = setup(null);
  assert.equal(sw.get('/build-info.json?check=123'), undefined);
  assert.equal(sw.get('/version.json'), undefined);
});
