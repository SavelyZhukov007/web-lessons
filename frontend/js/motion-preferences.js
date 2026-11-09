const reducedMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');

export function prefersReducedMotion() {
  return globalThis.document?.documentElement.dataset.nativeScreenReader === 'true' || !!reducedMotion?.matches || globalThis.document?.documentElement.dataset.reduceMotion === 'true';
}
