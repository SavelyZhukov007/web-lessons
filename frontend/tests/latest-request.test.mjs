import test from 'node:test';
import assert from 'node:assert/strict';
import { latestRequest } from '../js/latest-request.js';

test('a newer request aborts transport and invalidates a late successful response', async () => {
  const requests = latestRequest();
  const old = requests.begin();
  let finish;
  const lateResponse = new Promise(resolve => { finish = resolve; }).then(() => old.isCurrent());
  const next = requests.begin();
  finish();
  assert.equal(await lateResponse, false);
  assert.equal(old.signal.aborted, true);
  assert.equal(next.isCurrent(), true);
});
test('typing cancels immediately before the next debounced request starts', () => {
  const requests = latestRequest();
  const old = requests.begin();
  requests.cancel();
  assert.equal(old.isCurrent(), false);
  assert.equal(old.signal.aborted, true);
  assert.equal(requests.begin().isCurrent(), true);
});
