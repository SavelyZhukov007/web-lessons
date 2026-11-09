import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildPrintDays, normalizeEvent, weekFromQuery, weekRange, dateHuman, PRINT_DAYS } from '../js/print-logic.js';
import { parseDate, dateKey } from '../js/schedule-dates.js';

const MON = parseDate('2026-11-09');
const base = { event_id: 'e1', club_id: 1, club_name: 'Шахматы', date: '2026-11-10', start_time: '10:00', end_time: '11:00',
  status: 'scheduled', room_name: '101', leader_name: 'Иванов', category_name: 'Игры' };

test('неделя из ?week=: любой день → понедельник, мусор → текущая', () => {
  const today = parseDate('2026-11-04');
  assert.equal(dateKey(weekFromQuery('?week=2026-11-12', today)), '2026-11-09');
  assert.equal(dateKey(weekFromQuery('?week=bad', today)), '2026-11-02');
  assert.equal(dateKey(weekFromQuery('', today)), '2026-11-02');
  assert.equal(dateKey(weekFromQuery('?week=1990-01-01', today)), '2026-11-02');
});

test('диапазон печати совпадает с главным экраном: Пн–Сб', () => {
  assert.equal(PRINT_DAYS, 6);
  assert.equal(dateKey(weekRange(MON).end), '2026-11-14');
  assert.equal(buildPrintDays([], MON).length, 6);
});

test('нет room_names/leader_names — подставляются одиночные поля или заглушки', () => {
  assert.equal(normalizeEvent(base).rooms, '101');
  assert.equal(normalizeEvent({ ...base, room_names: ['101', '102'], leader_names: ['А', 'Б'] }).leaders, 'А, Б');
  const bare = normalizeEvent({ ...base, room_name: undefined, leader_name: '' });
  assert.equal(bare.rooms, 'Аудитория не указана');
  assert.equal(bare.leaders, 'Руководитель не указан');
});

test('битые события пропускаются, а не роняют страницу', () => {
  const days = buildPrintDays([null, 5, { ...base, date: 'x' }, { ...base, start_time: '12:00' }, { ...base, club_name: '' }, base], MON);
  assert.equal(days.flatMap(d => d.rows).length, 1);
  assert.equal(normalizeEvent({ ...base, status: 'weird' }).status, 'scheduled');
  assert.deepEqual(buildPrintDays('nope', MON).flatMap(d => d.rows), []);
});

test('перенос в другую неделю: старый слот «Перенесено на …», новый день «Перенесено с …» (кириллица)', () => {
  const moved = { ...base, event_id: 'm', status: 'moved', date: '2026-11-18', start_time: '12:00', end_time: '13:00',
    original_date: '2026-11-09', original_start_time: '10:00', original_end_time: '11:00' };
  const oldWeek = buildPrintDays([moved], MON);
  const ghost = oldWeek[0].rows[0];
  assert.equal(ghost.note, 'Перенесено на 18.11.2026, 12:00');
  assert.equal(ghost.ghost, true);
  assert.equal(ghost.slotStart, '10:00');
  const newWeek = buildPrintDays([moved], parseDate('2026-11-16'));
  const row = newWeek[2].rows[0];
  assert.equal(row.note, 'Перенесено с 09.11.2026, 10:00');
  assert.match(row.note, /^Перенесено с /u);
  assert.doesNotMatch(row.note, / c /);
});

test('отменённое помечено, порядок по времени, dateHuman', () => {
  const days = buildPrintDays([{ ...base, start_time: '12:00', end_time: '13:00', event_id: 'b' }, { ...base, status: 'cancelled' }], MON);
  assert.deepEqual(days[1].rows.map(r => r.slotStart), ['10:00', '12:00']);
  assert.equal(days[1].rows[0].note, 'Отменено');
  assert.equal(dateHuman(parseDate('2026-01-05')), '05.01.2026');
});

test('print.js/html: без отладки и заглушек, дата исходного занятия через parseDate', () => {
  const js = readFileSync(new URL('../js/print.js', import.meta.url), 'utf8') + readFileSync(new URL('../js/print-logic.js', import.meta.url), 'utf8');
  const html = readFileSync(new URL('../print.html', import.meta.url), 'utf8');
  assert.doesNotMatch(js, /console\.log|WTF|new Date\(event\.original_date\)/);
  assert.doesNotMatch(html, /week1|Is it needed/);
  assert.match(js, /parseDate\(e\.originalDate\)/);
});

test('главный экран: ссылка «Печать» ведёт на print.html?week=<понедельник>', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const js = readFileSync(new URL('../js/schedule-ui.js', import.meta.url), 'utf8');
  assert.match(html, /id="print-week"[^>]*href="\/print\.html"[^>]*>Печать</);
  assert.match(js, /\$\('print-week'\)\.href = `\/print\.html\?week=\$\{dateKey\(state\.week\)\}`/);
});


test('перенос внутри одной недели печатает исходный и новый слоты', () => {
  const e = { ...base, status: 'moved', original_date: '2026-11-10', original_start_time: '09:00',
    original_end_time: '10:00' };
  const rows = buildPrintDays([e], MON)[1].rows;
  assert.deepEqual(rows.map(r => [r.slotStart, r.ghost]), [['09:00', true], ['10:00', false]]);
});
