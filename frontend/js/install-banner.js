// Небольшая плашка «Установить приложение» на страницах сайта: iPhone → /ios, Android → /android/.
// Не показывается: на компьютере, внутри установленного PWA/нативного приложения, после закрытия (30 дней).
(() => {
    const KEY = 'clubs.installBanner.hiddenUntil';
    const ua = navigator.userAgent || '';
    const ios = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
    const android = /Android/i.test(ua);
    const standalone = navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
    const native = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
    if ((!ios && !android) || standalone || native) return;
    try { if (Number(localStorage.getItem(KEY) || 0) > Date.now()) return; } catch { /* приватный режим */ }
    const main = document.querySelector('main');
    if (!main) return;
    if (!document.querySelector('link[href="/css/distribution.css"]')) {
        const css = document.createElement('link');
        css.rel = 'stylesheet'; css.href = '/css/distribution.css';
        document.head.appendChild(css);
    }
    const href = ios ? '/ios' : '/android/';
    const box = document.createElement('aside');
    box.className = 'install-banner';
    box.setAttribute('aria-label', 'Установка приложения');
    box.innerHTML = `<img src="/icons/apple-touch-icon.png" alt="">
        <div class="install-banner__text"><strong>Установить приложение</strong><span>${ios ? 'На экран «Домой» — в два касания' : 'Расписание и уведомления на Android'}</span></div>
        <a class="btn btn--tonal btn--small install-banner__cta" href="${href}">Установить</a>
        <button class="install-banner__close" type="button" aria-label="Скрыть">×</button>`;
    box.querySelector('button').addEventListener('click', () => {
        try { localStorage.setItem(KEY, String(Date.now() + 30 * 864e5)); } catch { /* ignore */ }
        box.remove();
    });
    main.prepend(box);
})();
