// Public unfiltered weeks only. Preferences/auth never enter this database.
export const MAX_WEEK_AGE = 48 * 3600_000;
const LIMIT = 12, DB = 'kipclub.schedule.v1';
export function validWeekRecord(row, now = Date.now()) {
  return !!row && row.schema === 1 && Array.isArray(row.events) && Number.isFinite(row.savedAt)
    && row.savedAt <= now + 60_000 && now - row.savedAt <= MAX_WEEK_AGE;
}
const origin = () => {
  try { return new URL(globalThis.window?.AppServer?.get?.() || globalThis.location?.origin).origin; }
  catch { return 'local'; }
};
let database;
function open() {
  if (!globalThis.indexedDB) return Promise.resolve(null);
  if (database) return database;
  database = new Promise(resolve => {
    let settled = false;
    const finish = value => { if (settled) { value?.close(); return; } settled = true; clearTimeout(timer); resolve(value); };
    const timer = setTimeout(() => finish(null), 800);
    try {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore('weeks', { keyPath: 'key' });
      request.onsuccess = () => {
        request.result.onversionchange = () => { request.result.close(); database = null; };
        finish(request.result);
      };
      request.onerror = request.onblocked = () => finish(null);
    } catch { finish(null); }
  });
  return database;
}
async function transaction(mode, action) {
  const db = await open();
  if (!db) return null;
  return new Promise(resolve => {
    try {
      const tx = db.transaction('weeks', mode); let result;
      action(tx.objectStore('weeks'), value => { result = value; });
      tx.oncomplete = () => resolve(result);
      tx.onerror = tx.onabort = () => resolve(null);
    } catch { database = null; resolve(null); }
  });
}
export function createWeekStore() {
  const source = origin();
  const native = globalThis.window?.Capacitor?.isNativePlatform?.()
    ? globalThis.window.Capacitor.Plugins?.ItcNative : null;
  const key = week => `${source}|${week}`;
  return {
    async read(week) {
      let row;
      try {
        if (native?.readWeek) row = await native.readWeek({ origin: source, week });
        else row = await transaction('readonly', (store, done) => { const r = store.get(key(week)); r.onsuccess = () => done(r.result); });
        if (!validWeekRecord(row)) {
          // Migrate only the exact public unfiltered legacy week, never scan auth/preferences.
          try {
            const old = JSON.parse(globalThis.localStorage?.getItem('itc.cache:/api/schedule?week=' + week) || 'null');
            row = old && { schema: 1, events: old.b, savedAt: old.t, migrated: true };
          } catch { row = null; }
        }
        if (!validWeekRecord(row)) return null;
        return row;
      } catch { return null; }
    },
    async write(week, events, savedAt = Date.now()) {
      if (!validWeekRecord({ schema: 1, events, savedAt })) return;
      try {
        if (native?.writeWeek) { await native.writeWeek({ origin: source, week, events, savedAt }); return; }
        await transaction('readwrite', store => {
          store.put({ key: key(week), schema: 1, origin: source, week, events, savedAt });
          const request = store.getAll();
          request.onsuccess = () => {
            const rows = request.result.sort((a, b) => b.savedAt - a.savedAt);
            rows.forEach((row, index) => { if (index >= LIMIT || !validWeekRecord(row)) store.delete(row.key); });
          };
        });
      } catch { /* storage is optional, network remains usable */ }
    },
    async clear() {
      try {
        if (native?.clearWeeks) { await native.clearWeeks({ origin: source }); return; }
        await transaction('readwrite', store => {
          const r = store.openCursor();
          r.onsuccess = () => { const cursor = r.result; if (!cursor) return; if (cursor.value.origin === source) cursor.delete(); cursor.continue(); };
        });
      } catch { /* optional */ }
    },
  };
}
