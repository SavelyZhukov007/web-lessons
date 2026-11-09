import { prefersReducedMotion } from './motion-preferences.js';

export function bindGlassIndicator(group, selected, { signal } = {}) {
  const pill = document.createElement('span');
  pill.className = 'glass-indicator';
  pill.setAttribute('aria-hidden', 'true');
  group.prepend(pill);
  let previous;

  function update() {
    const active = selected();
    if (active !== previous) {
      if (previous) resize.unobserve(previous);
      if (active) resize.observe(active);
      previous = active;
    }
    if (!active?.offsetWidth) { pill.classList.remove('is-visible'); return; }
    pill.style.width = `${active.offsetWidth}px`;
    pill.style.height = `${active.offsetHeight}px`;
    pill.style.transform = `translate3d(${active.offsetLeft}px, ${active.offsetTop}px, 0)`;
    pill.classList.add('is-visible');
  }

  const resize = new ResizeObserver(update);
  resize.observe(group);
  group.addEventListener('change', update, { signal });
  signal?.addEventListener('abort', () => resize.disconnect(), { once: true });
  return update;
}

export async function mountGlassOptics(host, { signal } = {}) {
  const reduced = matchMedia('(prefers-reduced-transparency: reduce)');
  const forced = matchMedia('(forced-colors: active)');
  const layer = document.createElement('span');
  layer.className = 'glass-optics';
  layer.setAttribute('aria-hidden', 'true');
  host.prepend(layer);

  let instance;
  let starting = false;
  const stop = () => {
    instance?.destroy();
    instance = null;
    host.removeAttribute('data-glass-backend');
  };
  async function update() {
    if (reduced.matches || forced.matches || signal?.aborted || !host.isConnected || !host.offsetWidth) { stop(); return; }
    if (instance || starting) return;
    starting = true;
    try {
      const { attach, probeCapabilities } = await import('../vendor/liquidglass/index.js');
      // An actual backdrop is sampled on Blink. On other engines the same
      // controls use native CSS blur without cloning the surrounding DOM.
      if (signal?.aborted || reduced.matches || forced.matches || !host.offsetWidth || !probeCapabilities().backdropFilterUrl) return;
      instance = attach(layer, {
        preset: 'regular', backend: 'css-svg', physics: false, adaptive: true,
        blur: 7, frost: 0.15, refraction: 0.55, dispersion: 0,
        shadow: false, quality: { mapSide: 192, caPasses: 0, maxDpr: 1 },
      });
      const showBackend = () => { host.dataset.glassBackend = instance.backend; };
      showBackend();
      instance.on('backendchange', showBackend);
    } catch {
      stop();
    } finally {
      starting = false;
    }
  }
  const resize = new ResizeObserver(update);
  resize.observe(host);
  for (const mode of [reduced, forced]) mode.addEventListener('change', update, { signal });
  signal?.addEventListener('abort', () => { stop(); resize.disconnect(); layer.remove(); }, { once: true });
}

export function animatePanel(panel, open) {
  for (const animation of panel.getAnimations?.() || []) animation.cancel();
  if (open && !prefersReducedMotion()) {
    panel.animate?.([{ opacity: 0, transform: 'translateY(-5px)' }, { opacity: 1, transform: 'none' }],
      { duration: 180, easing: 'cubic-bezier(.2,.7,.2,1)' });
  }
}

export function toggleGlassPanel(panel, open) {
  panel.inert = !open;
  if (open) {
    panel.hidden = false;
    animatePanel(panel, true);
    return;
  }
  if (prefersReducedMotion() || !panel.animate) { panel.hidden = true; return; }
  animatePanel(panel, false);
  const exit = panel.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(-5px)' }],
    { duration: 140, easing: 'ease-out' });
  exit.finished.then(() => { if (panel.inert) panel.hidden = true; }, () => {});
}
