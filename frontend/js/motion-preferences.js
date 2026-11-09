const reducedMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');

export function prefersReducedMotion() {
  return !!reducedMotion?.matches || globalThis.document?.documentElement.dataset.reduceMotion === 'true';
}
