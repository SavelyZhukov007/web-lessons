const kinds = new Set(["leaders", "rooms"]);
export function favorites(kind, storage = globalThis.localStorage) {
  if (!kinds.has(kind)) return [];
  try {
    return JSON.parse(storage.getItem("kc.favorites." + kind) || "[]")
      .filter(
        (x) => Number.isInteger(x.id) && x.id > 0 && typeof x.name === "string",
      )
      .slice(0, 50);
  } catch {
    return [];
  }
}
export function toggleFavorite(
  kind,
  id,
  name,
  storage = globalThis.localStorage,
) {
  if (!kinds.has(kind) || !Number.isInteger(id) || id <= 0)
    throw new Error("Некорректное избранное");
  const list = favorites(kind, storage),
    on = !list.some((x) => x.id === id);
  if (on && list.length >= 50) throw new Error("В избранном уже 50 записей");
  storage.setItem(
    "kc.favorites." + kind,
    JSON.stringify(
      on
        ? [...list, { id, name: String(name).slice(0, 120) }]
        : list.filter((x) => x.id !== id),
    ),
  );
  return on;
}
export function liveState(event, now = Date.now()) {
  if (event.status === "cancelled" || event.ghost) return null;
  const start = Date.parse(event.date + "T" + event.start_time + ":00+03:00");
  const end = Date.parse(event.date + "T" + event.end_time + ":00+03:00");
  if (!(start < end)) return null;
  if (start <= now && now < end)
    return {
      kind: "now",
      label: "Сейчас · ещё " + Math.ceil((end - now) / 60000) + " мин",
      progress: (now - start) / (end - start),
    };
  const left = (start - now) / 60000;
  return left > 0 && left <= 15
    ? {
        kind: "soon",
        label: "Через " + Math.ceil(left) + " мин",
        progress: 1 - left / 15,
      }
    : null;
}
const escape = (value) =>
  String(value || "")
    .replace(/\\/g, "\\\\")
    .replace(/\r?\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
export function foldIcs(line) {
  const lines = [];
  let current = "",
    size = 0;
  for (const char of line) {
    const n = new TextEncoder().encode(char).length;
    if (size + n > 75) {
      lines.push(current);
      current = " ";
      size = 1;
    }
    current += char;
    size += n;
  }
  lines.push(current);
  return lines.join("\r\n");
}
export function eventCalendar(event, now = Date.now()) {
  if (event.status === "cancelled") throw new Error("Занятие отменено");
  const utc = (day, time) =>
    new Date(day + "T" + time + ":00+03:00")
      .toISOString()
      .replace(/[-:]|\.\d{3}/g, "");
  const uid = encodeURIComponent(event.event_id) + "@kipclub";
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//KipClub//Schedule//RU",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    "UID:" + uid,
    "DTSTAMP:" + new Date(now).toISOString().replace(/[-:]|\.\d{3}/g, ""),
    "DTSTART:" + utc(event.date, event.start_time),
    "DTEND:" + utc(event.date, event.end_time),
    "SUMMARY:" + escape(event.club_name),
    "LOCATION:" + escape((event.room_names || [event.room_name]).join(", ")),
    "DESCRIPTION:" +
      escape(
        (event.leader_names || [event.leader_name]).join(", ") +
          (event.comment ? "\n" + event.comment : ""),
      ),
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ]
    .map(foldIcs)
    .join("\r\n");
}
