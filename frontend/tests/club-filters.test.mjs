import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../js/club-filters.js', import.meta.url), 'utf8');
const { readClubFilters, buildClubUrl } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
);

test('пустой адрес даёт пустые фильтры', () => {
  assert.deepEqual(readClubFilters(''), { search: '', category_id: '' });
});
test('читаем русский поиск и ID направления', () => {
  assert.deepEqual(readClubFilters('?search=робот&category_id=2'),
    { search: 'робот', category_id: '2' });
});
test('убираем пробелы по краям и ограничиваем длину', () => {
  assert.equal(readClubFilters('?search=%20робот%20').search, 'робот');
  assert.equal(readClubFilters('?search=' + 'я'.repeat(250)).search.length, 200);
});
test('невалидный ID направления не сохраняется', () => {
  for (const value of ['0', '-1', 'abc', '2.5']) {
    assert.equal(readClubFilters('?category_id=' + value).category_id, '');
  }
});
test('сохраняем чужие параметры и якорь', () => {
  const next = buildClubUrl('https://example.test/clubs.html?source=chat#public-main',
    { search: 'робот', category_id: '2' });
  const url = new URL(next, 'https://example.test');
  assert.equal(url.pathname, '/clubs.html');
  assert.equal(url.searchParams.get('source'), 'chat');
  assert.equal(url.searchParams.get('search'), 'робот');
  assert.equal(url.searchParams.get('category_id'), '2');
  assert.equal(url.hash, '#public-main');
});
test('сброс удаляет только параметры фильтра', () => {
  assert.equal(buildClubUrl('https://example.test/clubs.html?source=chat&search=robot&category_id=2#public-main',
    { search: '', category_id: '' }), '/clubs.html?source=chat#public-main');
});
test('спецсимволы не ломают query строку', () => {
  const next = buildClubUrl('https://example.test/clubs.html',
    { search: 'C++ & Python', category_id: '' });
  assert.equal(new URL(next, 'https://example.test').searchParams.get('search'), 'C++ & Python');
});
test('чистые функции не меняют исходные данные', () => {
  const values = { search: ' робот ', category_id: '2' };
  buildClubUrl('https://example.test/clubs.html', values);
  assert.deepEqual(values, { search: ' робот ', category_id: '2' });
});
