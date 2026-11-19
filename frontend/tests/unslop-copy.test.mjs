import test from 'node:test';
import assert from 'node:assert/strict';
import { lessonCountLabel } from '../js/public-display.js';
import { showsCampusTour } from '../js/campus-tour.js';

test('статус расписания: число занятий со склонением, отмены только если есть', () => {
  assert.equal(lessonCountLabel(4, 2), '4 занятия, отменено 2');
  assert.equal(lessonCountLabel(1, 0), '1 занятие');
  assert.equal(lessonCountLabel(5), '5 занятий');
  assert.equal(lessonCountLabel(21, 1), '21 занятие, отменено 1');
  assert.equal(lessonCountLabel(0, 3), '0 занятий, отменено 3');
});

test('3D-тур в окне занятия — только у очных занятий с аудиторией', () => {
  assert.equal(showsCampusTour({ room_id: 3, is_remote: false }), true);
  assert.equal(showsCampusTour({ room_ids: [3, 4] }), true);
  assert.equal(showsCampusTour({ room_id: 3, is_remote: true }), false);
  assert.equal(showsCampusTour({ room_id: null, room_ids: [] }), false);
  assert.equal(showsCampusTour(null), false);
});
