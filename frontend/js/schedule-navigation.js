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
export function createDayRibbon(rail, selectDate) {
  const buttons = new Map();
  const indicator = bindGlassIndicator(rail, () => rail.querySelector('[aria-pressed="true"]'));
  mountGlassOptics(rail.parentElement);
  let selected;
  let first;
  let recenterFrame;

  function center(smooth) {
    const button = buttons.get(selected);
    const slot = rail.clientWidth / 6;
    if (!button || !slot) return;
    const left = button.offsetLeft - 2 * slot;
    rail.scrollTo({ left, behavior: smooth && !prefersReducedMotion() ? 'smooth' : 'auto' });
  }

  function update(date, today, events) {
    const key = dateKey(date);
    const changed = key !== selected;
    const markers = dayMarkers(events);
    const focusInRail = rail.contains(document.activeElement);
    let rebuilt = false;
    const windowStart = first ? stepStudyDay(first, 5) : null;
    const windowEnd = first ? stepStudyDay(first, 24) : null;
    if (!first || date < windowStart || date > windowEnd) {
      first = stepStudyDay(date, -14);
      rebuilt = true;
      const next = new Set();
      const list = [];
      for (let offset = 0; offset < 30; offset++) {
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
    if (changed) {
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
  new ResizeObserver(() => {
    cancelAnimationFrame(recenterFrame);
    recenterFrame = requestAnimationFrame(() => center(false));
  }).observe(rail);
  return update;
}

export function bindDaySwipe(content, step, enabled) {
  let swipe;
  content.addEventListener('touchstart', event => {
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
    if (event.cancelable) event.preventDefault();
  }, { passive: false });
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
