import test from 'node:test';
import assert from 'node:assert/strict';
import { CASCADE, cascadeTiming, cascadeOrder, runCascade } from '../js/skeleton-cascade.js';

test('каскад укладывается в cap при любом числе карточек', () => {
  for (const n of [0, 1, 2, 5, 9, 30, 200]) {
    const t = cascadeTiming(n, 12);
    assert.ok(t.total <= CASCADE.cap, `n=${n}: ${t.total}`);
    assert.equal(t.cards.length, n);
    assert.equal(t.skeletons.length, 12);
  }
});

test('шаг 45 мс для небольшой недели, карточки идут по возрастанию задержки', () => {
  const t = cascadeTiming(3, 2);
  assert.deepEqual(t.cards.map(c => c.delay), [60, 105, 150]);
  assert.equal(t.shift, 8);
});

test('большая неделя: шаг сжимается, чтобы уложиться в cap', () => {
  const t = cascadeTiming(40, 0);
  const step = t.cards[1].delay - t.cards[0].delay;
  assert.ok(step < CASCADE.step && step > 0);
  assert.equal(t.total, CASCADE.cap);
});

test('пустая неделя: только заглушки гаснут', () => {
  const t = cascadeTiming(0, 12);
  assert.equal(t.cards.length, 0);
  assert.ok(t.total > 0 && t.total <= CASCADE.cap);
  assert.equal(cascadeTiming(0, 0).total, 0);
});

test('prefers-reduced-motion: один fade без каскада и сдвига', () => {
  const t = cascadeTiming(9, 12, { reduced: true });
  assert.equal(t.shift, 0);
  assert.ok(t.cards.every(c => c.delay === 0 && c.duration === CASCADE.reduced));
  assert.equal(t.total, CASCADE.reduced);
});

test('порядок: сверху вниз, затем слева направо', () => {
  assert.deepEqual(cascadeOrder([{ top: 200, left: 0 }, { top: 10, left: 300 }, { top: 10, left: 100 }]), [2, 1, 0]);
});

test('без Web Animations API заглушки просто убираются', async () => {
  let removed = 0;
  const c = runCascade([{ remove: () => removed++ }], [], {});
  await c.finished;
  c.cancel();
  assert.equal(removed, 1);
});
