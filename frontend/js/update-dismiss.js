// Плашка «Доступна новая версия»: закрытие запоминается для конкретной версии (build id).
// Та же версия при автопроверках и перезагрузках больше не показывается; новая версия — показывается;
// ручная проверка («Проверить обновления») показывает результат всегда.
export const DISMISS_KEY = 'clubs.update.dismissed';

function store(storage) {
  try { return storage ?? globalThis.localStorage ?? null; } catch { return null; }
}

export function dismissedVersion(storage) {
  try { return store(storage)?.getItem(DISMISS_KEY) || null; } catch { return null; }
}

export function rememberDismiss(version, storage) {
  if (!version) return;
  try { store(storage)?.setItem(DISMISS_KEY, String(version)); } catch { /* хранилище недоступно */ }
}

export function shouldShowUpdate(version, { manual = false, storage } = {}) {
  if (manual) return true;
  return !version || dismissedVersion(storage) !== String(version);
}
