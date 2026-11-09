import { prefersReducedMotion } from './motion-preferences.js';

const loadEngine = () => import('../vendor/liquidglass/index.js');
let springMotion;

function enableSpringMotion() {
  if (springMotion || !CSS.supports('transition-timing-function', 'linear(0, 1)')) return;
  // Sample the vendored LiquidGlassJS spring once. CSS handles interruption
  // and interpolation without a JavaScript animation loop per control.
  springMotion = loadEngine().then(({ Spring }) => {
    const spring = new Spring(0, { stiffness: 500, damping: 30, mass: 1 });
    spring.target = 1;
    const samples = ['0'];
    for (let frame = 1; frame < 20; frame++) {
      spring.step(1 / 120);
      spring.step(1 / 120);
      samples.push(spring.value.toFixed(4));
    }
    document.documentElement.style.setProperty('--glass-spring', `linear(${samples.join(', ')}, 1)`);
  }).catch(() => {});
}

export function bindGlassIndicator(group, selected, { signal } = {}) {
  enableSpringMotion();
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
  const contrast = matchMedia('(prefers-contrast: more)');
  const layer = document.createElement('span');
  layer.className = 'glass-optics';
  layer.setAttribute('aria-hidden', 'true');
  host.prepend(layer);

  let instance;
  let starting = false;
  const disabled = () => reduced.matches || forced.matches || contrast.matches || document.documentElement.dataset.solidGlass === 'true';
  const stop = () => {
    instance?.destroy();
    instance = null;
    host.removeAttribute('data-glass-backend');
  };
  async function update() {
    if (disabled() || signal?.aborted || !host.isConnected || !host.offsetWidth) { stop(); return; }
    if (instance || starting) return;
    starting = true;
    try {
      const { attach, probeCapabilities } = await loadEngine();
      // An actual backdrop is sampled on Blink. On other engines the same
      // controls use native CSS blur without cloning the surrounding DOM.
      if (signal?.aborted || disabled() || !host.offsetWidth || !probeCapabilities().backdropFilterUrl) return;
      instance = attach(layer, {
        preset: 'clear', backend: 'css-svg', physics: false, adaptive: true,
        blur: 4, frost: 0.08, refraction: 0.82, specular: 0.7, dispersion: 0,
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
  for (const mode of [reduced, forced, contrast]) mode.addEventListener('change', update, { signal });
  window.addEventListener('clubs:themechange', update, { signal });
  signal?.addEventListener('abort', () => { stop(); resize.disconnect(); layer.remove(); }, { once: true });
}

export function animatePanel(panel, open) {
  for (const animation of panel.getAnimations?.() || []) animation.cancel();
  if (open && !prefersReducedMotion()) {
    const easing = document.documentElement.style.getPropertyValue('--glass-spring') || 'cubic-bezier(.2,.8,.2,1)';
    panel.animate?.([{ opacity: 0, transform: 'translateY(-5px) scale(.985)' }, { opacity: 1, transform: 'none' }],
      { duration: 260, easing });
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
