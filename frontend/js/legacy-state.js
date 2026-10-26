// Только наследие посещаемости. Избранное, тема, подписки и действующая авторизация сохраняются.
export function migrateLegacyState(storage, indexed = globalThis.indexedDB) {
  try {
    storage ||= globalThis.localStorage;
    let session;
    try { session = JSON.parse(storage.getItem('itc.session')); } catch { /* повреждённая запись */ }
    if (['student', 'teacher'].includes(session?.role) || (!session?.role && ['student', 'teacher'].includes(storage.getItem('itc.role')))) {
      storage.setItem('itc.session', JSON.stringify({ role: 'guest' }));
      storage.setItem('itc.role', 'guest');
    }
    const keys = ['itc.vault.v1', 'itc.checkinQueue', 'itc.studentName', 'itc.teacher.session'];
    if (keys.some(key => storage.getItem(key) !== null)) {
      for (const key of keys) storage.removeItem(key);
      try { indexed?.deleteDatabase('itc-secure'); } catch { /* недоступно */ }
    }
  } catch { /* localStorage может быть запрещён */ }
}
