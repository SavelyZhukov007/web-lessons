import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
const context = vm.createContext({});
vm.runInContext(readFileSync(new URL('../shim/performance-policy.js', import.meta.url), 'utf8'), context);
const { select, degrade } = context.ItcPerfPolicy;
const fast = { memoryGB: 8, cores: 8 };
test('capability tiers: low RAM, unknown, midrange, powerful', () => {
  assert.equal(select({ memoryGB: 2, cores: 8 }), 'none');
  assert.equal(select({ cores: 2 }), 'none');
  assert.equal(select({}), 'light');
  assert.equal(select({ memoryGB: 2.74, cores: 4 }), 'none');
  assert.equal(select({ memoryGB: 4, cores: 4 }), 'light');
  assert.equal(select(fast), 'full');
});
for (const setting of ['powerSave', 'nativeGpuOverloaded', 'reducedTransparency', 'solidGlass', 'lowRam']) {
  test(`${setting} always overrides the full material`, () => assert.equal(select({ ...fast, [setting]: true }), 'none'));
}
test('probe respects actual refresh budget, not a hardcoded 60fps assumption', () => {
  assert.equal(degrade('full', Array(60).fill(16.67), 60), 'full');
  assert.equal(degrade('full', Array(60).fill(16.67), 120), 'light');
  assert.equal(degrade('light', Array(60).fill(40), 60), 'none');
  assert.equal(degrade('none', Array(60).fill(40), 60), 'none');
});
test('short probes cannot cause a tier change; a good run cannot silently upgrade', () => {
  assert.equal(degrade('full', Array(20).fill(40), 60), 'full');
  assert.equal(degrade('none', Array(60).fill(8.33), 120), 'none');
});

test('runtime probe accumulates short interactions without an idle FPS timer', () => {
  let now = 0, next, id = 0;
  const root = { dataset: {}, toggleAttribute() {}, removeAttribute() {} };
  const window = { Capacitor: { isNativePlatform: () => true }, ItcPerfPolicy: context.ItcPerfPolicy,
    addEventListener() {}, dispatchEvent() {} };
  const runtime = vm.createContext({ window, document: { documentElement: root, hidden: false, addEventListener() {} },
    navigator: { deviceMemory: 8, hardwareConcurrency: 8 }, matchMedia: () => ({ matches: false, addEventListener() {} }),
    CustomEvent: class {}, performance: { now: () => now }, requestAnimationFrame: cb => { next = cb; return ++id; }, cancelAnimationFrame: () => { next = null; } });
  vm.runInContext(readFileSync(new URL('../shim/native-performance.js', import.meta.url), 'utf8'), runtime);
  function step(ms) { now += ms; const cb = next; next = null; cb?.(now); }
  for (let burst = 0; burst < 8; burst++) {
    window.ItcPerformance.beginMotion(220);
    for (let frame = 0; frame < 12; frame++) step(16.67);
    step(100);
    assert.equal(next, null, 'no RAF remains while idle');
  }
  assert.ok(window.ItcPerformance.stats.probes >= 1);
  assert.equal(window.ItcPerformance.tier, 'full');
});

test('severe foreground stalls trigger a short probe; one hiccup does not', () => {
  assert.equal(context.ItcPerfPolicy.shouldProbe([300, 300, ...Array(6).fill(16.67)]), true);
  assert.equal(degrade('full', [300, 300, ...Array(6).fill(16.67)], 60), 'light');
  assert.equal(degrade('full', [400, ...Array(7).fill(16.67)], 60), 'full');
});
test('blur pauses before the first RAF; late RAF debt is measured, not discarded', () => {
  let now = 0, next, id = 0; const attrs = new Set();
  const root = { dataset: {}, toggleAttribute(k,v) { v ? attrs.add(k) : attrs.delete(k); }, removeAttribute(k) {attrs.delete(k);} };
  const window = { Capacitor: { isNativePlatform: () => true }, ItcPerfPolicy: context.ItcPerfPolicy, addEventListener() {}, dispatchEvent() {} };
  const runtime = vm.createContext({ window, document: { documentElement: root, hidden: false, addEventListener() {} },
    navigator: { deviceMemory: 8, hardwareConcurrency: 8 }, matchMedia: () => ({ matches: false, addEventListener() {} }),
    CustomEvent: class {}, performance: { now: () => now }, requestAnimationFrame: cb => { next = cb; return ++id; }, cancelAnimationFrame: () => { next = null; } });
  vm.runInContext(readFileSync(new URL('../shim/native-performance.js', import.meta.url), 'utf8'), runtime);
  function step(ms) { now += ms; const cb = next; next = null; cb?.(now); }
  for (let burst=0;burst<8;burst++) {
    window.ItcPerformance.beginMotion(220);
    assert.ok(attrs.has('data-perf-motion'), 'pause is synchronous, even if the GPU is blocking RAF');
    step(600); assert.ok(attrs.has('data-perf-motion'), 'late first RAF still delivers a no-blur frame');
    for(let f=0;f<6;f++)step(16.67);
    step(200); assert.equal(next,null);
  }
  assert.ok(window.ItcPerformance.stats.probes >= 2);
  assert.equal(window.ItcPerformance.tier,'none');
});
