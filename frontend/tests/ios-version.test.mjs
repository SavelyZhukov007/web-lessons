import test from 'node:test';
import assert from 'node:assert/strict';
import { parseIosVersion, isTooOld, tooOldMessage } from '../js/ios-version.js';

const IPHONE = (v) => `Mozilla/5.0 (iPhone; CPU iPhone OS ${v} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1`;

test('iPhone OS 16_3 → 16.3', () => assert.equal(parseIosVersion(IPHONE('16_3')).text, '16.3'));
test('с патчем: 15_8_2 → 15.8.2', () => assert.deepEqual(parseIosVersion(IPHONE('15_8_2')), { major: 15, minor: 8, patch: 2, text: '15.8.2' }));
test('iPad: CPU OS 16_3', () => assert.equal(parseIosVersion('Mozilla/5.0 (iPad; CPU OS 16_3 like Mac OS X) Safari/604.1').text, '16.3'));
test('только мажор: iPhone OS 17 → 17.0', () => assert.equal(parseIosVersion('(iPhone; CPU iPhone OS 17 like Mac OS X)').text, '17.0'));
test('запасной Version/16.3 на iPhone', () => assert.equal(parseIosVersion('Mozilla/5.0 (iPhone) Version/16.3 Mobile Safari').text, '16.3'));
test('Mac/Android/пусто → null', () => {
    assert.equal(parseIosVersion('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.0 Safari/605.1.15'), null);
    assert.equal(parseIosVersion('Mozilla/5.0 (Linux; Android 14) Chrome/120'), null);
    assert.equal(parseIosVersion(''), null);
    assert.equal(parseIosVersion(undefined), null);
});
test('порог 16.4', () => {
    assert.equal(isTooOld(parseIosVersion(IPHONE('16_3_1'))), true);
    assert.equal(isTooOld(parseIosVersion(IPHONE('15_0'))), true);
    assert.equal(isTooOld(parseIosVersion(IPHONE('16_4'))), false);
    assert.equal(isTooOld(parseIosVersion(IPHONE('17_1'))), false);
    assert.equal(isTooOld(null), false);
});
test('текст с версией и путём в настройках', () => {
    const s = tooOldMessage(parseIosVersion(IPHONE('16_3')));
    assert.match(s, /iOS 16\.3 — она слишком старая/);
    assert.match(s, /Настройки → Основные → Обновление ПО/);
});
