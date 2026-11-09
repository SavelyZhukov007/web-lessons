import { addDays, dateKey, DAY_SHORT, monday, movedFromSlot, parseDate, WEEK_MAX, WEEK_MIN } from './schedule-dates.js';
import { bindGlassIndicator, mountGlassOptics } from './glass.js';
import { prefersReducedMotion } from './motion-preferences.js';

export function stepStudyDay(date, offset) {
  const direction = Math.sign(offset);
  for (let count = 0; count < Math.abs(offset); count++) {
    date = addDays(date, direction);
    if (date.getDay() === 0) date = addDays(date, direction);
  }
  return date;
}

export const weekInRange = date => {
  const key = dateKey(monday(date));
  return key >= WEEK_MIN && key <= WEEK_MAX;
};

const markLabels = { scheduled: 'есть занятия', moved: 'есть переносы', cancelled: 'есть отмены' };
const dayLabel = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
export function dayMarkers(events) {
  const markers = new Map();
  function put(key, status) {
    if (!markers.has(key)) markers.set(key, new Set());
    markers.get(key).add(status);
  }
  for (const event of events) {
    if (event.status !== 'cancelled') put(event.date, 'scheduled');
    if (event.status !== 'scheduled') put(event.date, event.status);
    if (movedFromSlot(event)) put(event.original_date, 'moved');
  }
  return markers;
}

// Keep a rolling set of buttons mounted, so keyboard focus and an animated
// selection survive the Saturday–Monday transition.
export function createDayRibbon(rail, selectDate, shiftWeek) {
  if (window.ItcPerformance?.enabled) return createTransformRibbon(rail, selectDate, shiftWeek);
  const buttons = new Map();
  const indicator = bindGlassIndicator(rail, () => rail.querySelector('[aria-pressed="true"]'));
  mountGlassOptics(rail.parentElement);
  let selected;
  let first;
  let recenterFrame;
  let fixed;
  let lastRender;
  const fixedWeek = () => document.documentElement.dataset.dayNavigation === 'week';

  function center(smooth) {
    if (fixed) { rail.scrollLeft = 0; return; }
    const button = buttons.get(selected);
    const slot = rail.clientWidth / 6;
    if (!button || !slot) return;
    const left = button.offsetLeft - 2 * slot;
    rail.scrollTo({ left, behavior: smooth && !prefersReducedMotion() ? 'smooth' : 'auto' });
  }

  function update(date, today, events) {
    lastRender = [date, today, events];
    const key = dateKey(date);
    const changed = key !== selected;
    const modeChanged = fixed !== fixedWeek();
    fixed = fixedWeek();
    const markers = dayMarkers(events);
    const focusInRail = rail.contains(document.activeElement);
    let rebuilt = false;
    const week = monday(date);
    const sameWindow = first && (fixed ? dateKey(first) === dateKey(week)
      : date >= stepStudyDay(first, 5) && date <= stepStudyDay(first, 24));
    if (modeChanged || !sameWindow) {
      first = fixed ? week : stepStudyDay(date, -14);
      rebuilt = true;
      const next = new Set();
      const list = [];
      for (let offset = 0; offset < (fixed ? 6 : 30); offset++) {
        const current = stepStudyDay(first, offset);
        const id = dateKey(current);
        next.add(id);
        let button = buttons.get(id);
        if (!button) {
          button = document.createElement('button');
          button.type = 'button';
          button.dataset.dayDate = id;
          button.dataset.dayLabel = dayLabel.format(current);
          const label = document.createElement('span');
          label.className = 'ribbon-weekday';
          label.textContent = DAY_SHORT[current.getDay() - 1];
          const number = document.createElement('strong');
          number.textContent = String(current.getDate());
          const dots = document.createElement('span');
          dots.className = 'ribbon-dots';
          dots.setAttribute('aria-hidden', 'true');
          button.append(label, number, dots);
          button.disabled = !weekInRange(current);
          button.addEventListener('click', () => selectDate(current));
          buttons.set(id, button);
        }
        list.push(button);
      }
      for (const id of buttons.keys()) if (!next.has(id)) buttons.delete(id);
      // Do not detach existing buttons while extending the window.
      for (const button of rail.querySelectorAll('[data-day-date]')) if (!next.has(button.dataset.dayDate)) button.remove();
      let before = rail.querySelector('[data-day-date]');
      for (const button of list) {
        if (button !== before) rail.insertBefore(button, before);
        before = button.nextElementSibling;
      }
    }
    selected = key;
    for (const [id, button] of buttons) {
      const types = markers.get(id) || new Set();
      const label = button.dataset.dayLabel;
      const suffix = [...types].map(type => markLabels[type]).join(', ');
      const accessible = suffix ? `${label}, ${suffix}` : label;
      if (button.getAttribute('aria-label') !== accessible) button.setAttribute('aria-label', accessible);
      if (changed || rebuilt) {
        button.setAttribute('aria-pressed', String(id === key));
        button.tabIndex = id === key ? 0 : -1;
      }
      button.classList.toggle('is-today', id === dateKey(today));
      const dots = button.querySelector('.ribbon-dots');
      if (dots.dataset.types !== suffix) {
        dots.dataset.types = suffix;
        dots.replaceChildren(...[...types].map(type => {
          const dot = document.createElement('i');
          dot.className = `ribbon-dot ${type}`;
          return dot;
        }));
      }
    }
    indicator();
    if (changed || modeChanged) {
      if (focusInRail) buttons.get(key)?.focus({ preventScroll: true });
      center(!rebuilt);
    }
  }

  rail.addEventListener('keydown', event => {
    const button = event.target.closest('[data-day-date]');
    if (!button) return;
    const key = event.key;
    const offset = { ArrowLeft: -1, ArrowRight: 1, PageUp: -6, PageDown: 6 }[key];
    if (!offset && key !== 'Home' && key !== 'End') return;
    event.preventDefault();
    const date = parseDate(button.dataset.dayDate);
    const target = offset ? stepStudyDay(date, offset) : addDays(monday(date), key === 'Home' ? 0 : 5);
    if (weekInRange(target)) selectDate(target);
  });
  bindDaySwipe(rail, shiftWeek, fixedWeek);
  window.addEventListener('clubs:themechange', () => {
    if (lastRender && fixed !== fixedWeek()) update(...lastRender);
  });
  new ResizeObserver(() => {
    cancelAnimationFrame(recenterFrame);
    recenterFrame = requestAnimationFrame(() => center(false));
  }).observe(rail);
  return update;
}

export function bindDaySwipe(content, step, enabled) {
  let swipe;
  const passive = !!window.ItcPerformance?.enabled;
  content.addEventListener('touchstart', event => {
    window.ItcPerformance?.beginMotion(280);
    const touch = event.touches[0];
    swipe = enabled() && event.touches.length === 1 && touch.clientX > 24 && touch.clientX < innerWidth - 24
      ? { x: touch.clientX, y: touch.clientY, time: event.timeStamp, horizontal: false, dx: 0 }
      : null;
  }, { passive: true });
  content.addEventListener('touchmove', event => {
    if (!swipe) return;
    if (event.touches.length !== 1) { swipe = null; return; }
    const { clientX, clientY } = event.touches[0];
    const dx = clientX - swipe.x;
    const dy = clientY - swipe.y;
    if (!swipe.horizontal) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 12) return;
      if (Math.abs(dx) < 1.4 * Math.abs(dy)) { swipe = null; return; }
      swipe.horizontal = true;
    }
    swipe.dx = dx;
    window.ItcPerformance?.beginMotion(280);
    if (!passive && event.cancelable) event.preventDefault();
  }, { passive });
  content.addEventListener('touchcancel', () => { swipe = null; });
  content.addEventListener('touchend', event => {
    if (!swipe?.horizontal) { swipe = null; return; }
    const { dx, time } = swipe;
    swipe = null;
    const distance = Math.abs(dx);
    if (distance >= 54 || (distance >= 26 && distance / Math.max(1, event.timeStamp - time) > 0.4)) {
      step(dx < 0 ? 1 : -1);
    }
  }, { passive: true });
}

// Android path: fixed-width slots and one compositor transform, all geometry from ResizeObserver.
// The ordinary web/PWA path remains unchanged until the native-only policy is installed.
function createTransformRibbon(rail, selectDate, shiftWeek) {
  const track = document.createElement('div'); track.className = 'ribbon-track';
  const pill = document.createElement('span'); pill.className = 'glass-indicator is-visible'; pill.setAttribute('aria-hidden', 'true');
  track.append(pill); rail.classList.add('ribbon-transform'); rail.append(track);
  let buttons = [], firstKey, currentKey, fixed, slot = 0, x = 0, pillX = 0, animation, pending, last;
  const fixedWeek = () => document.documentElement.dataset.dayNavigation === 'week';
  const easing = CSS.supports('animation-timing-function', 'linear(0, 1)')
    ? 'linear(0, .17, .44, .68, .85, .96, 1.02, 1.04, 1.03, 1.01, 1)' : 'cubic-bezier(.2,.8,.2,1)';
  function position(smooth) {
    if (!slot || !currentKey) return;
    const index = buttons.findIndex(b => b.dataset.dayDate === currentKey);
    if (index < 0) return;
    const target = fixed ? 0 : -(index - 2) * slot;
    // One read when interrupting an animation, never in an animation-frame loop.
    const moving = fixed ? pill : track;
    let start = fixed ? pillX : x;
    if (animation) {
      start = new DOMMatrixReadOnly(getComputedStyle(animation.effect.target).transform).m41;
      animation.cancel(); animation = null;
    }
    pill.style.transform = `translate3d(${index * slot}px,0,0)`;
    track.style.transform = `translate3d(${target}px,0,0)`;
    x = target; pillX = index * slot;
    const end = fixed ? pillX : target;
    if (smooth && start !== end && !prefersReducedMotion()) {
      window.ItcPerformance?.beginMotion(340);
      animation = moving.animate([{ transform: `translate3d(${start}px,0,0)` }, { transform: `translate3d(${end}px,0,0)` }], { duration: 320, easing });
      animation.id = 'itc-ribbon';
      const own = animation;
      own.finished.then(() => { if (animation === own) animation = null; }, () => {});
    }
  }
  function update(date, today, events) {
    last = [date, today, events];
    const key = dateKey(date), week = monday(date), mode = fixedWeek();
    const contains = buttons.findIndex(b => b.dataset.dayDate === key);
    const rebuild = fixed !== mode || !buttons.length || (mode ? firstKey !== dateKey(week) : contains < 5 || contains > 24);
    fixed = mode;
    if (rebuild) {
      const first = mode ? week : stepStudyDay(date, -14); firstKey = dateKey(first);
      const focused = rail.contains(document.activeElement);
      buttons.forEach(b => b.remove()); buttons = [];
      for (let i = 0; i < (mode ? 6 : 30); i++) {
        const day = stepStudyDay(first, i), id = dateKey(day);
        const button = document.createElement('button'); button.type = 'button'; button.dataset.dayDate = id;
        button.dataset.dayLabel = dayLabel.format(day); button.disabled = !weekInRange(day);
        const label = document.createElement('span'); label.className = 'ribbon-weekday'; label.textContent = DAY_SHORT[day.getDay() - 1];
        const number = document.createElement('strong'); number.textContent = String(day.getDate());
        const dots = document.createElement('span'); dots.className = 'ribbon-dots'; dots.setAttribute('aria-hidden', 'true');
        button.append(label, number, dots); button.addEventListener('click', () => selectDate(day)); buttons.push(button);
      }
      track.style.setProperty('--ribbon-count', String(buttons.length));
      track.append(...buttons);
      if (focused) buttons.find(b => b.dataset.dayDate === key)?.focus({ preventScroll: true });
    }
    const changed = key !== currentKey; currentKey = key;
    const markers = dayMarkers(events), now = dateKey(today);
    for (const button of buttons) {
      const id = button.dataset.dayDate, active = id === key;
      if (button.getAttribute('aria-pressed') !== String(active)) button.setAttribute('aria-pressed', String(active));
      button.tabIndex = active ? 0 : -1; button.classList.toggle('is-today', id === now);
      const types = [...(markers.get(id) || [])], suffix = types.map(t => markLabels[t]).join(', ');
      const label = `${button.dataset.dayLabel}${suffix ? `, ${suffix}` : ''}`;
      if (button.getAttribute('aria-label') !== label) button.setAttribute('aria-label', label);
      const dots = button.querySelector('.ribbon-dots');
      if (dots.dataset.types !== suffix) {
        dots.dataset.types = suffix;
        dots.replaceChildren(...types.map(type => { const dot = document.createElement('i'); dot.className = `ribbon-dot ${type}`; return dot; }));
      }
    }
    if (changed || rebuild) position(!rebuild);
  }
  new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    if (!width || slot === width / 6) return;
    slot = width / 6;
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => { rail.style.setProperty('--ribbon-slot', `${slot}px`); position(false); });
  }).observe(rail);
  rail.addEventListener('keydown', event => {
    const b = event.target.closest('[data-day-date]'); if (!b) return;
    const offset = { ArrowLeft: -1, ArrowRight: 1, PageUp: -6, PageDown: 6 }[event.key];
    if (!offset && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault(); const date = parseDate(b.dataset.dayDate);
    const next = offset ? stepStudyDay(date, offset) : addDays(monday(date), event.key === 'Home' ? 0 : 5);
    if (weekInRange(next)) selectDate(next);
  });
  bindDaySwipe(rail, delta => fixedWeek() ? shiftWeek(delta) : selectDate(stepStudyDay(parseDate(currentKey), delta)), () => true);
  window.addEventListener('clubs:themechange', () => { if (last && fixed !== fixedWeek()) update(...last); });
  return update;
}
