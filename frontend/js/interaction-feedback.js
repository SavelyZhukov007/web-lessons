const key = 'itc.haptics';

export function hasTapFeedback() {
  return !!window.ItcHaptics || (window.ClubsTheme.platform !== 'ios' && typeof navigator.vibrate === 'function' && matchMedia('(any-pointer: coarse)').matches);
}

export function tapFeedbackEnabled() {
  if (window.ItcHaptics) return window.ItcHaptics.on();
  try { return localStorage.getItem(key) === '1'; } catch { return false; }
}

export function tapFeedback() {
  if (!hasTapFeedback() || !tapFeedbackEnabled()) return;
  if (window.ItcHaptics) window.ItcHaptics.tap();
  else {
    try { navigator.vibrate(12); } catch { /* device or browser policy */ }
  }
}

export function setTapFeedback(value) {
  try {
    if (window.ItcHaptics) window.ItcHaptics.set(value);
    else localStorage.setItem(key, value ? '1' : '0');
  } catch { return; }
  if (value) tapFeedback();
}
