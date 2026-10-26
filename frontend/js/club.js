import { getClub, getRooms } from './api.js';
import { h, icon } from './ui.js';
import { mountClubPush } from './push.js';
import { monday, moscowToday, dateKey } from './schedule-dates.js';
import { calendarDate as formatDate, roomLabel } from './public-display.js';

const content = document.querySelector('#content');
const heading = document.querySelector('#club-name');
const badge = document.querySelector('#club-category');
const id = Number(new URLSearchParams(location.search).get('id'));

const DAYS = { 1: 'Понедельник', 2: 'Вторник', 3: 'Среда', 4: 'Четверг', 5: 'Пятница', 6: 'Суббота', 7: 'Воскресенье' };
let rooms = new Map();
let loadId = 0;

function sessionsBlock(club) {
  const items = [...club.sessions].sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time));
  return h('section', { 'aria-labelledby': 'sessions-title' }, h('h2', { id: 'sessions-title' }, 'Расписание'),
    items.length
      ? h('ul', { class: 'slot-list' }, items.map(s => h('li', {}, h('span', { class: 'slot-day' }, DAYS[s.weekday] || `День ${s.weekday}`),
        h('span', { class: 'slot-time' }, `${s.start_time}–${s.end_time}`), h('span', {}, roomLabel(s.room || rooms.get(s.room_id))))))
      : h('div', { class: 'empty-state' }, 'Занятий в расписании пока нет.'));
}

function changesBlock(club) {
  const sessions = new Map(club.sessions.map(s => [s.id, s]));
  const items = [...club.upcoming_exceptions].sort((a, b) => a.original_date.localeCompare(b.original_date));
  return h('section', { 'aria-labelledby': 'changes-title' }, h('h2', { id: 'changes-title' }, 'Ближайшие изменения'),
    items.length
      ? h('ul', { class: 'change-list' }, items.map(x => {
        const moved = x.type === 'moved';
        const s = sessions.get(x.session_id);
        return h('li', {}, h('span', { class: `badge ${moved ? 'badge--moved' : 'badge--cancelled'}` }, moved ? 'Перенос' : 'Отмена'),
          h('span', {}, moved
            ? `${formatDate(x.original_date)}${s ? ` ${s.start_time}` : ''} → ${formatDate(x.new_date)}, ${x.new_start_time}–${x.new_end_time}`
            : `${formatDate(x.original_date)}${s ? `, ${s.start_time}–${s.end_time}` : ''} — занятия не будет`),
          moved ? h('span', { class: 'change-room' }, `Новая аудитория: ${roomLabel(x.new_room || rooms.get(x.new_room_id), `№ ${x.new_room_id} — название пока недоступно`)}`) : null,
          x.comment ? h('span', { class: 'field-hint' }, x.comment) : null);
      }))
      : h('p', { class: 'directory-copy' }, 'Изменений нет — занятия идут по расписанию.'));
}

function render(club) {
  heading.textContent = club.name;
  document.title = `${club.name} — KipClub`;
  if (club.category?.name) {
    badge.textContent = club.category.name;
    badge.hidden = false;
  }
  const leader = club.leader;
  const facts = h('dl', { class: 'facts' });
  if (leader) {
    facts.append(h('dt', {}, 'Руководитель'), h('dd', {}, leader.name));
    if (leader.position) facts.append(h('dt', {}, 'Должность'), h('dd', {}, leader.position));
    if (leader.contact) facts.append(h('dt', {}, 'Контакты'), h('dd', {}, leader.contact));
  }
  const side = h('div', { class: 'column' },
    h('section', { class: 'card' }, h('h2', {}, 'О кружке'), facts.children.length ? facts : h('p', {}, 'Сведений о руководителе пока нет.'),
      h('div', { class: 'club-actions' }, h('a', { class: 'btn btn--tonal', href: `/api/clubs/${club.id}/calendar.ics?week=${dateKey(monday(moscowToday()))}` }, icon('calendar'), 'В календарь — текущая неделя (.ics)'))));
  const main = h('div', { class: 'column' }, sessionsBlock(club), changesBlock(club));
  content.replaceChildren(
    h('p', { class: 'detail-copy' }, club.description || 'Описание кружка пока не добавлено.'), main, side);
  mountClubPush(side, club.id).catch(() => {});
}

async function load() {
  const mine = ++loadId;
  content.setAttribute('aria-busy', 'true');
  try {
    const [clubResult, roomResult] = await Promise.allSettled([getClub(id), getRooms()]);
    if (mine !== loadId) return;
    if (clubResult.status === 'rejected') throw clubResult.reason;
    rooms = new Map(roomResult.status === 'fulfilled' ? roomResult.value.map(room => [room.id, room]) : []);
    render(clubResult.value);
    if (roomResult.status === 'rejected') content.append(h('div', { class: 'reference-error', role: 'status' },
      h('p', {}, 'Список аудиторий не загрузился. Номера переносов показаны без названий.'),
      h('button', { type: 'button', onclick: load }, 'Повторить загрузку аудиторий')));
  } catch (error) {
    if (error.status === 404) { heading.textContent = 'Кружок не найден'; document.title = 'Кружок не найден — KipClub'; }
    const box = h('div', { class: error.status === 404 ? 'empty-state' : 'error-state', role: error.status === 404 ? undefined : 'alert' }, h('p', {}, error.message));
    if (error.status !== 404) box.append(h('button', { type: 'button', class: 'btn btn--small', onclick: load }, 'Повторить попытку'));
    else box.append(h('a', { class: 'btn btn--tonal', href: '/clubs.html' }, 'К списку кружков'));
    content.replaceChildren(box);
  } finally {
    if (mine === loadId) content.setAttribute('aria-busy', 'false');
  }
}
load();
