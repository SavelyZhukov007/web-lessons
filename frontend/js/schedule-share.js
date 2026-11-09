import { eventCalendar } from './personal-schedule-model.js';
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
  const calendar = document.createElement('button');
  calendar.type = 'button';
  calendar.className = 'glass-action';
  calendar.textContent = 'В календарь телефона';
  calendar.disabled = event.status === 'cancelled';
  const calendarStatus = document.createElement('span');
  calendarStatus.setAttribute('role', 'status');
  calendarStatus.className = 'field-hint';
  calendarStatus.hidden = true;
  calendar.addEventListener('click', async () => {
    calendar.disabled = true;
    calendarStatus.hidden = true;
    try {
      const native = window.Capacitor?.Plugins?.ItcNative;
      try {
        if (native?.addToCalendar) {
          await native.addToCalendar({
            title: event.club_name,
            location: (event.room_names || [event.room_name]).join(', '),
            description: (event.leader_names || [event.leader_name]).join(', '),
            start: Date.parse(`${event.date}T${event.start_time}:00+03:00`),
            end: Date.parse(`${event.date}T${event.end_time}:00+03:00`),
          });
          return;
        }
      } catch (error) {
        if (error.name === 'AbortError') return;
      }
      const file = new File([eventCalendar(event)], `kipclub-${event.date}.ics`, { type: 'text/calendar' });
      const data = { files: [file] };
      try {
        if (navigator.share && navigator.canShare?.(data)) { await navigator.share(data); return; }
      } catch (error) {
        if (error.name === 'AbortError') return;
      }
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url;
      link.download = file.name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      calendarStatus.textContent = 'Не удалось сохранить календарь. Попробуйте ещё раз.';
      calendarStatus.hidden = false;
    } finally {
      calendar.disabled = false;
    }
  });
  actions.append(calendar, calendarStatus);
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
