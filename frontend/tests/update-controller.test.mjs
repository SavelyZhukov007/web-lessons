import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../js/update-controller.js', import.meta.url), 'utf8');

test('обновление не применяется само при фоновой проверке и установке воркера', () => {
  assert.doesNotMatch(src, /await apply\(\)/);
  assert.doesNotMatch(src, /showPending\(\);\s*if \(!hasUnsavedWork\(\)\) apply\(\)/);
  assert.match(src, /else if \(applying\) reload\(\); else showPending\(\);/);
});

test('ожидающая версия применяется только при холодном старте', () => {
  assert.match(src, /coldStart && !hasUnsavedWork\(\)\) apply\(\)/);
});
