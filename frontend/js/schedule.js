import {getSchedule} from './api.js';
const content = document.querySelector('#content');
try {
  const events = await getSchedule('2026-10-12');
  for (const event of events) {
    const item = document.createElement('p');
    item.textContent = `${event.date} · ${event.start_time}–${event.end_time} · ${event.club_name} · ${event.room_name}`;
    content.append(item);
  }
} catch (error) { content.textContent = error.message; }
