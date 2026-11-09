// Service worker сборки PWA (pwa/sw-pwa.js): значок на иконке по push и сообщениям страницы.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const file = fileURLToPath(new URL('../sw-pwa.js', import.meta.url));
const source = readFileSync(file, 'utf8');

function worker({ badging = true, brokenCaches = false, brokenBadge = false } = {}) {
  const store = new Map();
  const listeners = {};
  const badges = [];
  const cache = {
    async match(key) { const v = store.get(String(key)); return v === undefined ? undefined : new Response(v); },
    async put(key, response) { store.set(String(key), await response.text()); },
  };
  const navigator = badging ? {
    async setAppBadge(n) { if (brokenBadge) throw new Error('no badge'); badges.push(n); },
    async clearAppBadge() { badges.push(0); },
  } : {};
  const self = { navigator, addEventListener: (type, fn) => { listeners[type] = fn; } };
  const caches = { async open() { if (brokenCaches) throw new Error('quota'); return cache; } };
  vm.runInNewContext(source, { self, caches, Response, console }, { filename: file });
  async function fire(type, event) {
    let waiting = Promise.resolve();
    listeners[type]({ ...event, waitUntil: p => { waiting = p; } });
    await waiting;
  }
  return { store, badges, fire };
}

const push = data => ({ data: data === undefined ? null : { json: () => { if (data instanceof Error) throw data; return data; } } });

test('push прибавляет единицу к значку, badge:false не считается', async () => {
  const w = worker();
  await w.fire('push', push({ title: 'Отмена' }));
  await w.fire('push', push());
  await w.fire('push', push(new Error('text push')));
  await w.fire('push', push({ badge: false }));
  assert.equal(w.store.get('/__itc/badge'), '3');
  assert.deepEqual(w.badges, [1, 2, 3]);
});

test('страница задаёт счётчик и может выключить значок', async () => {
  const w = worker();
  await w.fire('message', { data: { type: 'itc-badge', count: 4, enabled: false } });
  assert.equal(w.store.get('/__itc/badge-enabled'), '0');
  await w.fire('push', push({}));
  assert.equal(w.store.get('/__itc/badge'), '4');
  await w.fire('message', { data: { type: 'itc-badge', count: 0, enabled: true } });
  await w.fire('push', push({}));
  assert.deepEqual(w.badges, [4, 0, 1]);
});

test('чужие и неверные сообщения игнорируются', async () => {
  const w = worker();
  for (const data of [null, { type: 'other', count: 1 }, { type: 'itc-badge', count: -1 }, { type: 'itc-badge', count: 1.5 }]) {
    await w.fire('message', { data });
  }
  assert.equal(w.store.size, 0);
  assert.deepEqual(w.badges, []);
});

test('без Badging API и без Cache Storage ничего не падает', async () => {
  const plain = worker({ badging: false });
  await plain.fire('message', { data: { type: 'itc-badge', count: 2 } });
  assert.equal(plain.store.get('/__itc/badge'), '2');
  const broken = worker({ brokenBadge: true });
  await broken.fire('message', { data: { type: 'itc-badge', count: 2 } });
  assert.equal(broken.store.get('/__itc/badge'), '2');
  const noCache = worker({ brokenCaches: true });
  await noCache.fire('message', { data: { type: 'itc-badge', count: 1, enabled: false } });
  await noCache.fire('push', push({}));
  assert.deepEqual(noCache.badges, [1, 1]);
});
