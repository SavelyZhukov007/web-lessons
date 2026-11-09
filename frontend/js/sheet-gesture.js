import { prefersReducedMotion } from './motion-preferences.js';

// A drag may dismiss only if it started at the top. Reaching the top midway
// through a scrolling gesture never turns that same gesture into a dismissal.
export function bindSheetDismiss(sheet, { scrollBody, close = () => sheet.close(), isOpen = () => sheet.open }) {
  let drag = null;

  function reset(animate = false) {
    const distance = drag?.distance || 0;
    drag = null;
    sheet.style.removeProperty('transform');
    if (animate && distance && !prefersReducedMotion()) {
      sheet.animate?.([{ transform: `translateY(${distance}px)` }, { transform: 'none' }], {
        duration: 160, easing: 'ease-out',
      });
    }
  }

  sheet.addEventListener('touchstart', event => {
    if (!isOpen() || sheet.classList.contains('m-closing')) return;
    reset();
    const body = scrollBody();
    if (event.touches.length !== 1 ||
        body?.scrollTop > 1 || event.target.closest('button, a, input, select, textarea, label, summary, [role="slider"]')) return;
    const touch = event.touches[0];
    drag = { x: touch.clientX, y: touch.clientY, start: event.timeStamp, distance: 0, locked: false };
  }, { passive: true });

  sheet.addEventListener('touchmove', event => {
    if (!drag) return;
    if (event.touches.length !== 1) { reset(); return; }
    const touch = event.touches[0];
    const dy = touch.clientY - drag.y;
    const dx = touch.clientX - drag.x;
    if (!drag.locked) {
      if (Math.max(Math.abs(dy), Math.abs(dx)) < 10) return;
      if (dy <= Math.abs(dx) * 1.25 || scrollBody()?.scrollTop > 1) { reset(); return; }
      drag.locked = true;
    }
    drag.distance = Math.max(0, dy);
    if (event.cancelable) event.preventDefault();
    if (!prefersReducedMotion()) sheet.style.transform = `translateY(${drag.distance}px)`;
  }, { passive: false });

  sheet.addEventListener('touchend', event => {
    if (!drag) return;
    const { distance, start } = drag;
    const quick = distance >= 54 && distance / Math.max(1, event.timeStamp - start) > 0.55;
    if (distance >= Math.min(120, sheet.offsetHeight * 0.28) || quick) {
      drag = null;
      close();
      if (!sheet.classList.contains('m-closing')) reset();
    } else reset(true);
  });
  sheet.addEventListener('touchcancel', () => reset(true));
  sheet.addEventListener('close', () => reset());
}
