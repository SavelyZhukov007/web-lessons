import test from 'node:test';
import assert from 'node:assert/strict';
import { clubColor } from '../js/event-colors.js';

test('кружки с общим серым направлением получают стабильные разные цвета', () => {
  const colors = Array.from({ length: 22 }, (_, index) => clubColor(index + 1, '#64748b', 'Без направления'));
  assert.equal(new Set(colors).size, 22);
  assert.equal(clubColor(2, '#64748b', 'Без направления'), colors[1]);
});

test('цвет указанного направления сохраняется', () => {
  assert.equal(clubColor(5, '#ABCDEF', 'Технологии'), '#abcdef');
});
