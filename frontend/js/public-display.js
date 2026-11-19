// Представление данных API без DOM: одинаковые подписи на публичных экранах и в админке.
import { parseDate, formatDate } from './schedule-dates.js';

export function calendarDate(value) {
  const date = parseDate(value);
  return date ? formatDate(date, { year: 'numeric' }) : String(value ?? '');
}

export function roomLabel(room, fallback = 'Аудитория не указана') {
  if (!room) return fallback;
  return [room.name, room.building].filter(value => String(value ?? '').trim()).join(' · ') || fallback;
}

export function eventRoom(event, rooms = new Map()) {
  if (event.room_ids?.length > 1) return event.room_ids.map(id => roomLabel(rooms.get(id), event.room_names?.[event.room_ids.indexOf(id)] || `№ ${id}`)).join(', ');
  const room = rooms.get(event.room_id);
  return roomLabel({ name: event.room_name || room?.name, building: event.room_building || room?.building });
}

// Строка статуса расписания: «4 занятия, отменено 2». Отмены — только если они есть.
export function lessonCountLabel(active, cancelled = 0) {
  const forms = { one: 'занятие', few: 'занятия', many: 'занятий', other: 'занятия' };
  const label = `${active} ${forms[new Intl.PluralRules('ru').select(active)]}`;
  return cancelled > 0 ? `${label}, отменено ${cancelled}` : label;
}
