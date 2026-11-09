// Логика печатной версии расписания (print.html) без DOM — покрыта node-тестами.
import { addDays, dateKey, minutes, parseDate, scheduleLocation, movedFromSlot } from './schedule-dates.js';

export const PRINT_DAYS = 6; // как на главном экране: Пн–Сб
export { WEEK_MIN, WEEK_MAX } from './schedule-dates.js';
export const STATUS_NAMES = { scheduled: 'По расписанию', moved: 'Перенесено', cancelled: 'Отменено' };

const TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

export function dateHuman(date) {
  return `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}.${date.getFullYear()}`;
}

/** Неделя из ?week=YYYY-MM-DD (любой день → понедельник); без параметра или вне диапазона — текущая. */
export function weekFromQuery(search, today) {
  const params = new URLSearchParams(search);
  params.delete('day');
  return scheduleLocation(params, today).week;
}

export function weekRange(weekStart) {
  return { start: weekStart, end: addDays(weekStart, PRINT_DAYS - 1) };
}

function names(list, single, fallback) {
  const items = Array.isArray(list) ? list.filter(x => typeof x === 'string' && x.trim()) : [];
  if (items.length) return items.join(', ');
  return typeof single === 'string' && single.trim() ? single : fallback;
}

/** Одно событие API → строка печати или null (битое событие пропускаем, а не роняем страницу). */
export function normalizeEvent(event) {
  if (!event || typeof event !== 'object') return null;
  if (!parseDate(event.date) || !TIME.test(event.start_time) || !TIME.test(event.end_time)) return null;
  if (minutes(event.start_time) >= minutes(event.end_time)) return null;
  if (typeof event.club_name !== 'string' || !event.club_name.trim()) return null;
  const status = Object.hasOwn(STATUS_NAMES, event.status) ? event.status : 'scheduled';
  const original = event.original_date && parseDate(event.original_date) ? event.original_date : null;
  return {
    id: typeof event.event_id === 'string' ? event.event_id : `${event.club_name}-${event.date}-${event.start_time}`,
    club: event.club_name,
    date: event.date,
    start: event.start_time,
    end: event.end_time,
    status,
    originalDate: original,
    originalStart: TIME.test(event.original_start_time) ? event.original_start_time : null,
    originalEnd: TIME.test(event.original_end_time) ? event.original_end_time : null,
    rooms: names(event.room_names, event.room_name, 'Аудитория не указана'),
    leaders: names(event.leader_names, event.leader_name, 'Руководитель не указан'),
  };
}

/** Строки печати по дням недели: перенесённые занятия стоят также в исходном слоте с пометкой «Перенесено на …». */
export function buildPrintDays(data, weekStart) {
  const { start, end } = weekRange(weekStart);
  const first = dateKey(start), last = dateKey(end);
  const inWeek = key => key >= first && key <= last;
  const rows = [];
  for (const raw of Array.isArray(data) ? data : []) {
    const e = normalizeEvent(raw);
    if (!e) continue;
    if (inWeek(e.date)) {
      let note = '';
      if (e.status === 'cancelled') note = STATUS_NAMES.cancelled;
      else if (movedFromSlot(raw)) note = `Перенесено с ${dateHuman(parseDate(e.originalDate))}${e.originalStart ? `, ${e.originalStart}` : ''}`;
      else if (e.status === 'moved') note = STATUS_NAMES.moved;
      rows.push({ ...e, slotDate: e.date, slotStart: e.start, slotEnd: e.end, note, ghost: false });
    }
    if (movedFromSlot(raw) && inWeek(e.originalDate)) {
      rows.push({
        ...e, slotDate: e.originalDate, slotStart: e.originalStart || e.start, slotEnd: e.originalEnd || e.end,
        rooms: names(raw.original_room_names, e.rooms, 'Аудитория не указана'),
        note: `Перенесено на ${dateHuman(parseDate(e.date))}, ${e.start}`, ghost: true,
      });
    }
  }
  rows.sort((a, b) => a.slotDate.localeCompare(b.slotDate) || a.slotStart.localeCompare(b.slotStart) || a.club.localeCompare(b.club, 'ru'));
  return Array.from({ length: PRINT_DAYS }, (_, i) => {
    const date = addDays(start, i);
    const key = dateKey(date);
    return { date, key, rows: rows.filter(r => r.slotDate === key) };
  });
}
