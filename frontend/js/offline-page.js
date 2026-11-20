// Офлайн-страница: счётчик offline_open (ляжет в очередь и уйдёт, когда появится сеть) и кнопка «Сообщить о проблеме».
import { usage } from './usage.js';

usage?.emit('offline_open');
const button = document.getElementById('offline-report');
const status = document.getElementById('offline-report-status');
button?.addEventListener('click', async () => {
  try {
    const { openFeedback } = await import('./feedback.js');
    openFeedback(button, { type: 'bug', source: 'offline' });
    if (navigator.onLine === false && status) status.textContent = 'Сообщение уйдёт, когда появится сеть: просто нажми «Отправить» ещё раз.';
  } catch {
    if (status) status.textContent = 'Форма откроется, когда появится сеть.';
  }
});
