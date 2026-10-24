import { isStandalone } from './push-support.js';

const platform = window.ClubsTheme?.platform || 'desktop';
const $ = id => document.getElementById(id);
const standalone = isStandalone(window);
const ua = navigator.userAgent || '';
const iosSafari = platform === 'ios' && /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|YaBrowser/i.test(ua);

const messages = {
  ios: iosSafari ? 'Ты на iPhone/iPad в Safari — выполни шаги ниже.' : 'Ты на iPhone/iPad, но не в Safari. Лучше открыть эту страницу в Safari и повторить шаги ниже.',
  android: 'Ты на Android — установка через Chrome, шаги ниже.',
  desktop: 'Ты за компьютером. Если нужен телефон — открой эту страницу на нём.',
};
$('install-detected').textContent = standalone ? 'Приложение уже запущено в режиме установленного.' : messages[platform];
$('install-already').hidden = !standalone;
// Показываем сначала инструкцию для своей платформы
for (const name of ['ios', 'android', 'desktop']) {
  const section = $(`install-${name}`);
  if (name === platform) section.classList.add('is-current'); else if (platform !== 'desktop') section.classList.add('is-other');
}
let deferred;
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  deferred = event;
  $('install-actions').hidden = false;
  $('install-button').hidden = false;
});
$('install-button').addEventListener('click', async () => {
  if (!deferred) return;
  deferred.prompt();
  await deferred.userChoice.catch(() => null);
  deferred = null;
  $('install-actions').hidden = true;
});
