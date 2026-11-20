// Informational notice. Anonymous statistics are on by default and can be switched off in settings (docs/privacy.md).
const noticeKey = 'kipclub.storage-notice.v1';
let acknowledged = false;
try { acknowledged = localStorage.getItem(noticeKey) === '1'; } catch { /* storage may be unavailable */ }

if (!acknowledged && !window.Capacitor?.isNativePlatform?.()) {
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = '/css/storage-notice.css';
  document.head.append(style);
  const notice = document.createElement('aside');
  notice.className = 'storage-notice';
  notice.setAttribute('aria-label', 'Информация о хранении данных');
  const text = document.createElement('p');
  text.textContent = 'Сайт хранит настройки и расписание на устройстве, а для входа сотрудников нужны cookie. Анонимную статистику можно выключить в настройках.';
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Понятно';
  button.addEventListener('click', () => {
    try { localStorage.setItem(noticeKey, '1'); } catch { /* hide for this visit */ }
    notice.remove();
  });
  notice.append(text, button);
  document.body.append(notice);
}
