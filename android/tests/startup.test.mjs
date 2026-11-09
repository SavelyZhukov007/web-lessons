import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../shim/app-splash.js', import.meta.url), 'utf8');
test('cold splash has one RAF chain even when progress advances repeatedly', () => {
  let frames = 0; const waits = [];
  const document = { readyState: 'loading', documentElement: { classList: { add() {}, remove() {} } }, addEventListener() {} };
  const window = { Capacitor: { isNativePlatform: () => true } };
  vm.runInNewContext(source, { window, document, sessionStorage: { getItem: () => null },
    performance: { now: () => 100 }, requestAnimationFrame: () => ++frames, cancelAnimationFrame() {},
    setTimeout: (fn, ms) => { waits.push(ms); }, clearInterval() {}, Math });
  window.ItcSplash.progress(.3); window.ItcSplash.progress(.5); window.ItcSplash.progress(.9);
  assert.equal(frames, 1);
  window.ItcSplash.done(); assert.deepEqual(waits, [0]);
  window.ItcSplash.done(); assert.deepEqual(waits, [0]);
});
test('native splash can release on committed pixels without waiting for JS RAF', () => {
  const activity = readFileSync(new URL('../native/java/ru/kipfin/clubs/MainActivity.java', import.meta.url), 'utf8');
  assert.match(activity, /addWebViewListener/); assert.match(activity, /onPageCommitVisible/);
});
