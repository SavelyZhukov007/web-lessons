// Обновление оболочки не прерывает несохранённую форму.
import './ping.js';
import './storage-notice.js';
import { migrateLegacyState } from './legacy-state.js';
import { startReleaseNotes } from './release-notes.js';
import { startUpdates } from './update-controller.js';
migrateLegacyState();
if (location.pathname === '/qr.html' || location.pathname.startsWith('/teacher/')) location.replace('/?from=legacy');
startUpdates();
startReleaseNotes();

// Best effort, never a claim that iOS cannot evict a PWA. No permission prompt on first load.
if (matchMedia('(display-mode: standalone)').matches || navigator.standalone === true) {
  const protect = () => { navigator.storage?.persist?.().catch(() => {}); };
  document.addEventListener('pointerdown', protect, { once: true, passive: true });
}
