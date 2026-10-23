export const DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
export const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

// Гражданские даты в полдень: календарный день не зависит от перевода часов.
export function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (year < 1900 || year > 9998) return null;
  const date = new Date(year, month - 1, day, 12);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

export function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function monday(date) {
  return addDays(date, -((date.getDay() + 6) % 7));
}

export function moscowToday() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return parseDate(`${values.year}-${values.month}-${values.day}`);
}

export function formatDate(date, options = {}) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', ...options }).format(date);
}

export function minutes(time) {
  const [hours, mins] = time.split(':').map(Number);
  return hours * 60 + mins;
}

// Параллельные занятия делят ширину дня. Соседние интервалы используют ту же полосу.
export function eventLanes(events) {
  const sorted = [...events].sort((a, b) => minutes(a.start_time) - minutes(b.start_time) || minutes(a.end_time) - minutes(b.end_time) || a.event_id.localeCompare(b.event_id));
  const result = [];
  let group = [];
  let laneEnds = [];
  let groupEnd = -1;
  function flush() {
    for (const item of group) result.push({ ...item, lanes: laneEnds.length });
    group = [];
    laneEnds = [];
  }
  for (const event of sorted) {
    const start = minutes(event.start_time);
    const end = minutes(event.end_time);
    if (start >= groupEnd) flush();
    let lane = laneEnds.findIndex(value => value <= start);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = end;
    group.push({ event, lane });
    groupEnd = group.length === 1 ? end : Math.max(groupEnd, end);
  }
  flush();
  return result;
}
