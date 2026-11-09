import { prepareScheduleSearch } from './schedule-search-index.js';
export function mountLazyScheduleSearch(options) {
  const input = document.getElementById('search');
  let api, pending, wanted = false, composing = false, events, controller, warmTimer;
  async function open() {
    wanted = true;
    pending ||= import('./schedule-search.js').then(module => {
      api = module.mountScheduleSearch(options); api.setComposing(composing); return api;
    }).catch(error => { pending = null; document.getElementById('search-status').textContent = 'Поиск не загрузился. Попробуй ещё раз.'; throw error; });
    try { const ready = await pending; if (wanted) ready.open(); } catch { /* a later focus retries */ }
  }
  input.addEventListener('focus', open); input.addEventListener('click', open);
  input.addEventListener('compositionstart', () => { composing = true; api?.setComposing(true); });
  input.addEventListener('compositionend', () => { composing = false; api?.setComposing(false); });
  return {
    render() {
      api?.render();
      if (options.state.phase !== 'ready' || events === options.state.events) return;
      events = options.state.events; controller?.abort(); controller = new AbortController();
      if (warmTimer) (window.cancelIdleCallback || clearTimeout)(warmTimer);
      const own = controller, current = events;
      warmTimer = (window.requestIdleCallback || (fn => setTimeout(fn, 300)))(() => {
        if (!own.signal.aborted && !document.hidden) prepareScheduleSearch(current, { signal: own.signal }).catch(() => {});
      }, { timeout: 1500 });
    },
    close(settings) { wanted = false; return api?.close(settings) || false; },
  };
}
