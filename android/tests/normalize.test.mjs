// node tests/normalize.test.mjs — нормализация адреса тестового сервера (app-shim.js)
import fs from 'node:fs'; import assert from 'node:assert/strict';
const src = fs.readFileSync(new URL('../shim/app-shim.js', import.meta.url), 'utf8');
const ctx = { window: { APP_DEMO_BUILD: 1 }, localStorage: { getItem: () => null }, location: { pathname: '/' }, document: { addEventListener() {} } };
new Function('window', 'localStorage', 'location', 'document', src)(ctx.window, ctx.localStorage, ctx.location, ctx.document);
const { normalize } = ctx.window.ItcServerTools;
const ok = { '192.168.1.5': 'http://192.168.1.5:8000', '192.168.1.5:8080': 'http://192.168.1.5:8080', 'http://host': 'http://host',
  'https://h.ru/': 'https://h.ru', 'h.local:9000/x': 'http://h.local:9000', ' 10.0.0.2 ': 'http://10.0.0.2:8000', 'HTTP://A.RU:80': 'http://a.ru' };
for (const [i, o] of Object.entries(ok)) assert.equal(normalize(i), o, i);
for (const bad of ['', 'ftp://a', 'http://a:70000', 'a b', 'http://']) assert.throws(() => normalize(bad), undefined, bad);
assert.equal(ctx.window.AppServer, undefined, 'в демо без выбранного сервера AppServer не включается');
console.log('normalize: OK', Object.keys(ok).length + 5, 'cases');
