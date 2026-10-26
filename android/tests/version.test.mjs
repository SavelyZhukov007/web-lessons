import test from 'node:test';
import assert from 'node:assert/strict';
import { parseId } from '../scripts/version.mjs';

test('public beta is a public channel, with its own stage', () => {
  assert.deepEqual(parseId('v1.0.012pb'), { id: 'v1.0.012pb', version: '1.0.012', channel: 'p', stage: 'b' });
});
test('previous releases retain their version identifiers', () => {
  assert.equal(parseId('v0.8.467pr').stage, 'r');
  assert.equal(parseId('v0.7.016ia').channel, 'i');
  assert.throws(() => parseId('v1.0.012unknown'));
});
