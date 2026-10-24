// Регистрирует service worker (офлайн-оболочка + push). Тихо ничего не делает там, где SW недоступны
// (http без localhost, старые браузеры, приватный режим Firefox).
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(error => console.warn('Service worker не зарегистрирован:', error));
  });
}
