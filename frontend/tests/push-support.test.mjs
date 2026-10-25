import test from 'node:test';
import assert from 'node:assert/strict';
import { pushAvailability, urlBase64ToUint8Array, isStandalone } from '../js/push-support.js';

const OK = { native: false, secure: true, hasSW: true, hasPush: true, hasNotification: true, platform: 'desktop', standalone: false, permission: 'default' };

test('всё есть → ok', () => assert.equal(pushAvailability(OK).state, 'ok'));
test('нативное приложение → свои уведомления (FCM / фоновая проверка)', () => {
  const r = pushAvailability({ ...OK, native: true });
  assert.equal(r.state, 'native');
  assert.match(r.message, /Firebase/);
});
test('http без localhost → insecure', () => assert.equal(pushAvailability({ ...OK, secure: false }).state, 'insecure'));
test('iOS в обычной вкладке Safari → нужно «На экран Домой»', () => {
  const r = pushAvailability({ ...OK, platform: 'ios', standalone: false, hasPush: false });
  assert.equal(r.state, 'ios-install');
  assert.match(r.message, /Домой/);
});
test('iOS установленное PWA с поддержкой → ok; без поддержки → нужен iOS 16.4', () => {
  assert.equal(pushAvailability({ ...OK, platform: 'ios', standalone: true }).state, 'ok');
  const r = pushAvailability({ ...OK, platform: 'ios', standalone: true, hasPush: false });
  assert.equal(r.state, 'unsupported');
  assert.match(r.message, /16\.4/);
});
test('нет PushManager / Notification → unsupported', () => {
  assert.equal(pushAvailability({ ...OK, hasPush: false }).state, 'unsupported');
  assert.equal(pushAvailability({ ...OK, hasNotification: false }).state, 'unsupported');
});
test('разрешение denied → denied', () => assert.equal(pushAvailability({ ...OK, permission: 'denied' }).state, 'denied'));
test('urlBase64ToUint8Array: base64url без паддинга', () => {
  assert.deepEqual([...urlBase64ToUint8Array('AQID')], [1, 2, 3]);
  assert.deepEqual([...urlBase64ToUint8Array('-_8')], [251, 255]);
  assert.equal(urlBase64ToUint8Array('BAAA').length, 3);
});
test('isStandalone: navigator.standalone и display-mode', () => {
  assert.equal(isStandalone({ navigator: { standalone: true } }), true);
  assert.equal(isStandalone({ navigator: {}, matchMedia: () => ({ matches: true }) }), true);
  assert.equal(isStandalone({ navigator: {}, matchMedia: () => ({ matches: false }) }), false);
  assert.equal(isStandalone({}), false);
});
