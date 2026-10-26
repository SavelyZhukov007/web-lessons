// Черновики живут только в текущей вкладке, не дольше суток. Пароли сюда не передаются.
const PREFIX = 'clubs.draft.v1:';
const MAX_AGE = 24 * 3600 * 1000;
function key(name) { return PREFIX + (window.ClubsAdmin?.login || 'admin') + ':' + name; }
export function readDraft(name) {
  try {
    const item = JSON.parse(sessionStorage.getItem(key(name)));
    if (!item || !Number.isFinite(item.at) || Date.now() - item.at > MAX_AGE) { clearDraft(name); return null; }
    return item.value;
  } catch { return null; }
}
export function writeDraft(name, value) {
  try { sessionStorage.setItem(key(name), JSON.stringify({ at: Date.now(), value })); } catch { /* закрытое хранилище */ }
}
export function clearDraft(name) { try { sessionStorage.removeItem(key(name)); } catch { /* закрытое хранилище */ } }
export function markUnsaved(root, dirty) {
  root.dataset.unsaved = String(!!dirty);
  document.dispatchEvent(new Event('app:draft-change'));
}
