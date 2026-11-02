import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DISMISS_KEY, dismissedVersion, rememberDismiss, shouldShowUpdate } from '../js/update-dismiss.js';

function mem() { const m = new Map(); return { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), m }; }

test('закрытая версия не показывается снова при автопроверке и перезагрузке', () => {
  const s = mem();
  assert.equal(shouldShowUpdate('b2', { storage: s }), true);
  rememberDismiss('b2', s);
  assert.equal(s.m.get(DISMISS_KEY), 'b2');
  assert.equal(shouldShowUpdate('b2', { storage: s }), false);
  assert.equal(dismissedVersion(s), 'b2');
});

test('новая версия показывается, ручная проверка — всегда', () => {
  const s = mem(); rememberDismiss('b2', s);
  assert.equal(shouldShowUpdate('b3', { storage: s }), true);
  assert.equal(shouldShowUpdate('b2', { storage: s, manual: true }), true);
});

test('неизвестная версия и недоступное хранилище не прячут плашку', () => {
  const broken = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } };
  assert.equal(shouldShowUpdate(null, { storage: mem() }), true);
  rememberDismiss('b2', broken);
  assert.equal(shouldShowUpdate('b2', { storage: broken }), true);
});

test('кнопка закрытия — иконка с aria-label и запоминанием версии', () => {
  const src = readFileSync(new URL('../js/update-controller.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src, /textContent = 'X'/);
  assert.match(src, /closeButton\.append\(icon\('close'\)\)/);
  assert.match(src, /aria-label', 'Закрыть уведомление об обновлении'/);
  assert.match(src, /rememberDismiss\(pendingVersion\(\)\)/);
  assert.match(src, /showPending\(\{ manual \}\)/);
});
