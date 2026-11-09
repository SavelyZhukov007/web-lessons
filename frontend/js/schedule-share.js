import { dateKey, monday, parseDate } from './schedule-dates.js';

export function eventUrl(event, origin) {
  const url = new URL('/', origin);
  url.searchParams.set('week', dateKey(monday(parseDate(event.date))));
  url.searchParams.set('day', event.date);
  url.searchParams.set('event', event.event_id);
  return url.href;
}

export function eventShareControls(event, clubLink) {
  const actions = document.createElement('div');
  actions.className = 'schedule-event-actions';
  actions.append(clubLink);
  const server = window.AppServer?.get();
  if (!server && window.DemoBackend && window.Capacitor?.isNativePlatform?.()) return actions;
  const url = eventUrl(event, server || location.origin);
  const share = document.createElement('button');
  share.type = 'button';
  share.className = 'glass-action';
  share.textContent = 'Поделиться занятием';
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  status.className = 'field-hint';
  const link = document.createElement('input');
  link.type = 'url';
  link.readOnly = true;
  link.value = url;
  link.hidden = true;
  link.setAttribute('aria-label', 'Ссылка на занятие');
  share.addEventListener('click', async () => {
    try {
      const native = window.Capacitor?.Plugins?.Share;
      if (native?.share) { await native.share({ title: event.club_name, url }); return; }
      if (navigator.share) { await navigator.share({ title: event.club_name, url }); return; }
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        status.textContent = 'Ссылка на занятие скопирована';
        return;
      }
    } catch (error) {
      if (error.name === 'AbortError') return;
    }
    link.hidden = false;
    link.focus();
    link.select();
  });
  actions.append(share, status, link);
  return actions;
}
