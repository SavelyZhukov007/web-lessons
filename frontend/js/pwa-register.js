// Обновление оболочки не прерывает несохранённую форму.
import './ping.js';
import './storage-notice.js';
import { migrateLegacyState } from './legacy-state.js';
import { startUpdates } from './update-controller.js';
migrateLegacyState();
if (location.pathname === '/qr.html' || location.pathname.startsWith('/teacher/')) location.replace('/?from=legacy');
startUpdates();
