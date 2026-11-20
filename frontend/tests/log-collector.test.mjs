import test from 'node:test';
import assert from 'node:assert/strict';
import { createCollector, install, fullVersion, scrub, deviceInfo } from '../js/log-collector.js';

test('ring buffer keeps last N entries', () => {
  const c = createCollector({ limit: 3 });
  for (let i = 0; i < 5; i++) c.console('warn', [`w${i}`]);
  assert.deepEqual(c.entries().map(e => e.msg), ['w2', 'w3', 'w4']);
});

test('secrets are scrubbed and query strings dropped', () => {
  const c = createCollector();
  c.console('error', ['login failed password=hunter2 Bearer abcdefghijkl']);
  c.fetch('/api/admin/x?token=zzz', 500, 12.4);
  const [a, b] = c.entries();
  assert.ok(!a.msg.includes('hunter2') && !a.msg.includes('abcdefghijkl'));
  assert.equal(b.url, '/api/admin/x'); assert.equal(b.status, 500); assert.equal(b.ms, 12); assert.equal(b.level, 'error');
  assert.equal(scrub('token: "abc"'), 'token: "[скрыто]"');
});

test('install hooks console, errors, rejections, failed fetch and navigation', async () => {
  const listeners = {};
  const logs = [];
  const win = {
    console: { error: (...a) => logs.push(a), warn: () => {} },
    addEventListener: (n, f) => { listeners[n] = f; },
    location: { href: 'http://host/index.html?x=1' },
    fetch: async url => (url === '/bad' ? { ok: false, status: 404 } : url === '/down' ? Promise.reject(new TypeError('net')) : { ok: true, status: 200 }),
  };
  const c = install(win);
  win.console.error('oops');
  assert.equal(logs.length, 1);
  listeners.error({ message: 'TypeError: x', error: { stack: 'at y' }, filename: 'http://host/js/a.js?v=1' });
  listeners.unhandledrejection({ reason: new Error('nope') });
  await win.fetch('/ok'); await win.fetch('/bad');
  await assert.rejects(win.fetch('/down'));
  win.location.href = 'http://host/#/clubs'; listeners.hashchange();
  const kinds = c.entries().map(e => `${e.kind}:${e.status ?? ''}`);
  assert.deepEqual(kinds, ['nav:', 'console:', 'error:', 'rejection:', 'fetch:404', 'fetch:0', 'nav:']);
  assert.equal(install(win), c, 'second install is a no-op');
});

test('full version id and device info', async () => {
  assert.equal(fullVersion('v1.7.829ib', 'W'), 'v1.7.829ibW');
  assert.equal(fullVersion('v1.7.829ibA', 'W'), 'v1.7.829ibA');
  assert.equal(fullVersion('', 'W'), '');
  const info = await deviceInfo({ ItcSplash: { version: 'v1.7.829ib' }, Capacitor: { isNativePlatform: () => true, Plugins: { Device: { getInfo: async () => ({ model: 'Pixel' }) } } },
    navigator: { userAgent: 'UA', language: 'ru', onLine: false }, screen: { width: 400, height: 800 }, innerWidth: 400, innerHeight: 700 });
  assert.equal(info.version, 'v1.7.829ibA'); assert.equal(info.platform, 'A'); assert.equal(info.online, false); assert.equal(info.device.model, 'Pixel');
});

test('device info has only short UA and no device name', async () => {
  const { shortUa } = await import('../js/log-collector.js');
  const ua = 'Mozilla/5.0 (Linux; Android 14; TECNO BF7n Build/UP1A; wv) AppleWebKit/537.36 Version/4.0 Chrome/131.0.6778.39 Mobile Safari/537.36';
  const info = await deviceInfo({ ItcSplash: { version: 'v1.9.024ib' }, Capacitor: { isNativePlatform: () => true, Plugins: { Device: { getInfo: async () => ({ name: 'Телефон Савелия', model: 'BF7n', osVersion: '14', webViewVersion: '131.0.1' }) } } },
    navigator: { userAgent: ua, language: 'ru' }, screen: { width: 1, height: 1 } });
  assert.equal(info.ua, 'Android 14 · WebView 131'); assert.equal(info.userAgent, undefined);
  assert.deepEqual(info.device, { model: 'BF7n', osVersion: '14', webViewMajor: 131 });
  assert.equal(shortUa('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Version/17.5 Mobile/15E148 Safari/604.1'), 'iOS 17 · Safari 17');
  assert.equal(shortUa('curl/8'), '');
});
