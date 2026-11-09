const mobile = matchMedia('(max-width: 999px), (any-pointer: coarse)');
const root = document.documentElement;
const selector = 'dialog[open], [role="dialog"][aria-modal="true"]:not([hidden])';
let saved;

function sync() {
  const open = mobile.matches && !!document.body.querySelector(selector);
  if (open && !saved) {
    saved = { x: window.scrollX, y: window.scrollY };
    root.style.setProperty('--modal-scroll-top', `${-saved.y}px`);
    root.setAttribute('data-modal-scroll-lock', '');
  } else if (!open && saved) {
    root.removeAttribute('data-modal-scroll-lock');
    root.style.removeProperty('--modal-scroll-top');
    window.scrollTo(saved.x, saved.y);
    saved = null;
  }
}

function start() {
  // Includes the native/PWA overlays. Keep the lock until the last window
  // closes, including the time spent in its exit animation.
  new MutationObserver(sync).observe(document.body, {
    childList: true, subtree: true, attributes: true, attributeFilter: ['open', 'hidden', 'aria-modal'],
  });
  mobile.addEventListener('change', sync);
  sync();
}

if (document.body) start();
else document.addEventListener('DOMContentLoaded', start, { once: true });
