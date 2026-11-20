// Анонимные счётчики расписания (общие для сайта js/schedule.js и APK app-schedule.js):
// schedule_view (сегодня / завтра / другой день / эта, следующая, другая неделя), schedule_nav tap,
// screen_view day|week, событие kc:schedule-view для карточки «Как тебе KipClub?», ttfs (время до расписания).
import { dateKey, addDays, monday, moscowToday } from './schedule-dates.js';

export function viewDim({ week, shown, dayMode, now = moscowToday() }) {
  if (dayMode) {
    const key = dateKey(shown);
    return key === dateKey(now) ? 'today' : key === dateKey(addDays(now, 1)) ? 'tomorrow' : 'day_other';
  }
  const start = dateKey(week), thisWeek = monday(now);
  return start === dateKey(thisWeek) ? 'week_this' : start === dateKey(addDays(thisWeek, 7)) ? 'week_next' : 'week_other';
}

export function createViewTracker(win = window, clock = () => performance.now()) {
  let last = '', first = true;
  return function track({ week, shown, dayMode, extra = '' }) {
    const dim = viewDim({ week, shown, dayMode });
    const key = `${dim}|${dateKey(week)}|${dateKey(shown)}|${extra}`;
    if (key === last) return false;
    if (last) win.KipUsage?.emit('schedule_nav', 'tap');
    last = key;
    win.KipUsage?.emit('schedule_view', dim);
    win.KipUsage?.emit('screen_view', dayMode ? 'day' : 'week');
    win.dispatchEvent?.(new CustomEvent('kc:schedule-view'));
    if (first) { first = false; win.KipUsage?.measure('ttfs', clock()); }
    return true;
  };
}
