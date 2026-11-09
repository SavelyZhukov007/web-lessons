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

function motionAllowed() {
  return !prefersReducedMotion() && document.documentElement.dataset.reduceMotion !== 'true';
}

function springEasing() {
  return document.documentElement.style.getPropertyValue('--glass-spring') || 'cubic-bezier(.2, .76, .26, 1)';
}

// Капля: на ходу индикатор вытягивается по направлению движения и пружиной возвращается к форме.
export function liquidStretch(pill, shift) {
  if (!pill.animate || !motionAllowed()) return;
  const stretch = Math.min(0.32, Math.abs(shift) / Math.max(pill.offsetWidth * 4, 1));
  if (stretch < 0.02) return;
  pill.getAnimations?.().forEach(animation => { if (animation.id === 'glass-stretch') animation.cancel(); });
  const animation = pill.animate([
    { scale: `${1 + stretch} ${1 - stretch * 0.45}`, transformOrigin: shift > 0 ? '100% 50%' : '0% 50%' },
    { scale: '1 1', transformOrigin: '50% 50%' },
  ], { duration: 460, easing: springEasing() });
  animation.id = 'glass-stretch';
}

// Блик под пальцем: кнопки из стекла «загораются» в точке касания, как в iOS 26.
let glintBound = false;
export function bindGlassGlint(root = document) {
  if (glintBound) return;
  glintBound = true;
  enableSpringMotion();
  root.addEventListener('pointerdown', event => {
    const target = event.target instanceof Element && event.target.closest('.glass-action, .glass-trigger, .glass-tabs > :is(button, a, label)');
    if (!target) return;
    const box = target.getBoundingClientRect();
    if (!box.width || !box.height) return;
    target.style.setProperty('--glass-hl-x', `${Math.round(((event.clientX - box.left) / box.width) * 100)}%`);
    target.style.setProperty('--glass-hl-y', `${Math.round(((event.clientY - box.top) / box.height) * 100)}%`);
  }, { passive: true, capture: true });
}

const mounted = new WeakSet();
const GLASS_HOSTS = '.glass-surface, .glass-tabs, dialog.sheet, #event-dialog, .itc-sheet-card';
let everywhere;

// Оптика LiquidGlassJS на каждой стеклянной поверхности (панели, полосы, табы, шторки) — один раз на элемент.
export function mountGlassEverywhere(root = document, { signal } = {}) {
  if (root === document && everywhere) return everywhere;
  bindGlassGlint();
  const mount = host => {
    if (mounted.has(host) || host.closest('[data-glass-static]')) return;
    mounted.add(host);
    mountGlassOptics(host, { signal });
  };
  const scan = node => {
    if (!(node instanceof Element)) return;
    if (node.matches(GLASS_HOSTS)) mount(node);
    node.querySelectorAll?.(GLASS_HOSTS).forEach(mount);
  };
  scan(root instanceof Document ? root.documentElement : root);
  const observer = new MutationObserver(records => {
    for (const record of records) record.addedNodes.forEach(scan);
  });
  observer.observe(root instanceof Document ? root.body : root, { childList: true, subtree: true });
  signal?.addEventListener('abort', () => observer.disconnect(), { once: true });
  if (root === document) everywhere = observer;
  return observer;
}

export function bindGlassIndicator(group, selected, { signal } = {}) {
  enableSpringMotion();
  const pill = document.createElement('span');
  pill.className = 'glass-indicator';
  pill.setAttribute('aria-hidden', 'true');
  group.prepend(pill);
  let previous;
  let lastLeft;

  function update() {
    const active = selected();
    if (active !== previous) {
      if (previous) resize.unobserve(previous);
      if (active) resize.observe(active);
      previous = active;
    }
    if (!active?.offsetWidth) { pill.classList.remove('is-visible'); return; }
    const shift = lastLeft === undefined ? 0 : active.offsetLeft - lastLeft;
    lastLeft = active.offsetLeft;
    pill.style.width = `${active.offsetWidth}px`;
    pill.style.height = `${active.offsetHeight}px`;
    pill.style.transform = `translate3d(${active.offsetLeft}px, ${active.offsetTop}px, 0)`;
    const wasVisible = pill.classList.contains('is-visible');
    pill.classList.add('is-visible');
    if (wasVisible && shift) liquidStretch(pill, shift);
  }

  const resize = new ResizeObserver(update);
  resize.observe(group);
  group.addEventListener('change', update, { signal });
  signal?.addEventListener('abort', () => resize.disconnect(), { once: true });
  return update;
}

export async function mountGlassOptics(host, { signal } = {}) {
  if (host.querySelector(':scope > .glass-optics')) return;
  mounted.add(host);
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
  if (open && motionAllowed()) {
    panel.animate?.([{ opacity: 0, transform: 'translateY(-8px) scale(.96)', filter: 'blur(3px)' }, { opacity: 1, transform: 'none', filter: 'none' }],
      { duration: 420, easing: springEasing() });
  }
}

export function toggleGlassPanel(panel, open) {
  panel.inert = !open;
  if (open) {
    panel.hidden = false;
    animatePanel(panel, true);
    return;
  }
  if (!motionAllowed() || !panel.animate) { panel.hidden = true; return; }
  animatePanel(panel, false);
  const exit = panel.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(-5px)' }],
    { duration: 140, easing: 'ease-out' });
  exit.finished.then(() => { if (panel.inert) panel.hidden = true; }, () => {});
}
