import { h, icon } from '../../ui.js';
import { loadAll, getStats } from '../api.js';
import { pageHeader, loading, formatDate, dayShort } from '../kit.js';
import { moscowToday, dateKey } from '../../schedule-dates.js';

export async function mount(root, { signal }) {
  root.replaceChildren(pageHeader('Обзор'), loading());
  const [data, stats] = await Promise.all([loadAll({ signal }), getStats({ signal }).catch(() => null)]);
  const today = dateKey(moscowToday());
  const upcoming = data.exceptions.filter(e => (e.new_date || e.original_date) >= today).sort((a, b) => a.original_date.localeCompare(b.original_date)).slice(0, 6);
  const stat = (href, value, label, iconName) => h('a', { class: 'stat-card', href }, icon(iconName), h('strong', {}, String(value)), h('span', {}, label));
  const changeLine = e => {
    const session = data.session.get(e.session_id);
    const club = session && data.club.get(session.club_id);
    const detail = e.type === 'moved' ? `перенос на ${formatDate(e.new_date)} ${e.new_start_time}–${e.new_end_time}, ${data.room.get(e.new_room_id)?.name ?? ''}` : 'отмена';
    return h('li', {}, h('span', { class: `badge badge--${e.type === 'moved' ? 'moved' : 'cancelled'}` }, e.type === 'moved' ? 'Перенос' : 'Отмена'),
      h('span', {}, `${club?.name ?? 'Занятие удалено'} · ${formatDate(e.original_date)}${session ? ` (${dayShort(session.weekday)} ${session.start_time})` : ''} — ${detail}`));
  };
  root.replaceChildren(...[
    pageHeader('Обзор'),
    h('div', { class: 'stat-grid' },
      stat('#/clubs', data.clubs.filter(c => c.is_active).length, `активных кружков (всего ${data.clubs.length})`, 'users'),
      stat('#/sessions', data.sessions.length, 'регулярных занятий', 'calendar'),
      stat('#/exceptions', upcoming.length, 'ближайших изменений', 'list'),
      stat('#/reference', data.rooms.length, 'аудиторий', 'book')),
    stats && usersCard(stats),
    h('section', { class: 'card' }, h('h2', {}, 'Ближайшие изменения расписания'),
      upcoming.length ? h('ul', { class: 'change-list' }, upcoming.map(changeLine)) : h('p', { class: 'field-hint' }, 'Отмен и переносов впереди нет.'),
      h('div', { class: 'form-actions' }, h('a', { class: 'btn btn--tonal', href: '#/exceptions' }, 'Отменить или перенести занятие'), h('a', { class: 'btn btn--tonal', href: '#/broadcasts' }, 'Отправить объявление'))),
    data.clubs.length === 0 && h('div', { class: 'empty-state' }, h('strong', {}, 'Пока нет ни одного кружка'), 'Начни со справочников (направление, руководитель, аудитория), потом добавь кружок.')].filter(Boolean));
  root.querySelector('#view-title').focus({ preventScroll: true });
}

// «Пользователи»: обезличенный счётчик (GET /api/admin/stats)
const KINDS = [['android-apk', 'Android'], ['ios-pwa', 'iPhone'], ['web', 'Браузер']];
function usersCard(s) {
  const row = (label, w) => h('tr', {}, h('th', { scope: 'row' }, label), h('td', {}, String(s.active[w].total)),
    ...KINDS.map(([k]) => h('td', {}, String(s.active[w][k]))));
  const fig = (value, label) => h('div', { class: 'users-fig' }, h('strong', {}, String(value)), h('span', {}, label));
  return h('section', { class: 'card users-card', dataset: { usersCard: '' } }, h('h2', {}, 'Пользователи'),
    h('div', { class: 'users-figs' }, fig(s.total, 'всего установок'), fig(s.new_week, 'новых за неделю'),
      fig(s.push.web + s.push.fcm, `push-подписок (веб ${s.push.web}, Android ${s.push.fcm})`), fig(s.admins, s.admins === 1 ? 'администратор' : 'администраторов')),
    h('div', { class: 'table-wrap' }, h('table', { class: 'users-table' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Активны'), h('th', {}, 'Всего'), ...KINDS.map(([, t]) => h('th', {}, t)))),
      h('tbody', {}, row('за день', 'day'), row('за неделю', 'week'), row('за месяц', 'month')))));
}
