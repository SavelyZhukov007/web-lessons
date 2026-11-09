import test from "node:test";
import assert from "node:assert/strict";
import {
  favorites,
  toggleFavorite,
  liveState,
  eventCalendar,
  foldIcs,
} from "../js/personal-schedule-model.js";
const base = {
  event_id: "1:2026-11-09",
  date: "2026-11-09",
  start_time: "15:00",
  end_time: "16:00",
  status: "scheduled",
  club_name: "Робототехника, код; тест\\текст",
  room_name: "101",
  leader_name: "Иванов",
};
const at = (t) => Date.parse("2026-11-09T" + t + ":00+03:00");
test("live clock is Moscow-time; all boundaries and cancellations", () => {
  assert.equal(liveState(base, at("14:44")), null);
  assert.equal(liveState(base, at("14:45")).kind, "soon");
  assert.equal(liveState(base, at("15:00")).kind, "now");
  assert.equal(liveState(base, at("15:30")).progress, 0.5);
  assert.equal(liveState(base, at("16:00")), null);
  assert.equal(liveState({ ...base, status: "cancelled" }, at("15:30")), null);
  assert.equal(liveState({ ...base, ghost: true }, at("15:30")), null);
});
test("favorite collections are independent, bounded, persist toggles and tolerate corrupt storage", () => {
  const m = new Map(),
    s = { getItem: (k) => m.get(k), setItem: (k, v) => m.set(k, v) };
  assert.equal(toggleFavorite("rooms", 1, "101", s), true);
  assert.equal(toggleFavorite("leaders", 1, "Иванов", s), true);
  assert.equal(toggleFavorite("rooms", 1, "101", s), false);
  assert.equal(favorites("leaders", s)[0].name, "Иванов");
  m.set("kc.favorites.rooms", "broken");
  assert.deepEqual(favorites("rooms", s), []);
  assert.throws(() => toggleFavorite("clubs", 1, "x", s));
  assert.throws(() => toggleFavorite("rooms", -1, "x", s));
  for (let i = 1; i <= 50; i++) toggleFavorite("rooms", i, "Аудитория", s);
  assert.throws(() => toggleFavorite("rooms", 51, "x", s));
});
test("one-event ICS keeps stable UID, escapes text and uses UTC correctly", () => {
  const text = eventCalendar(base, at("14:00")).replace(/\r\n /g, "");
  assert.match(text, /DTSTART:20261109T120000Z/);
  assert.match(text, /DTEND:20261109T130000Z/);
  assert.ok(
    text.includes(String.raw`SUMMARY:Робототехника\, код\; тест\\текст`),
  );
  assert.match(text, /UID:1%3A2026-11-09@kipclub/);
  assert.match(
    eventCalendar({ ...base, status: "moved", start_time: "17:00" }),
    /UID:1%3A2026-11-09@kipclub/,
  );
  assert.throws(() => eventCalendar({ ...base, status: "cancelled" }));
});
test("ICS folding never splits UTF-8 code points or exceeds 75 octets", () => {
  const text = "SUMMARY:" + "Русский текст 👨‍💻 ".repeat(30),
    folded = foldIcs(text);
  assert.equal(folded.replace(/\r\n /g, ""), text);
  for (const line of folded.split("\r\n"))
    assert.ok(Buffer.byteLength(line) <= 75);
});
