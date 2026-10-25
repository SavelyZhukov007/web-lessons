// Оболочка админки: проверка сессии, шапка/навигация, hash-роутер (#/clubs, #/reference/rooms …), перенаправление на вход при 401.
import { h, icon } from '../ui.js';
import { getAdminStatus, logout } from './api.js';
import { guarded } from './kit.js';

const ROUTES = {
  '': { title: 'Обзор', icon: 'home', load: () => import('./views/dashboard.js') },
  clubs: { title: 'Кружки', icon: 'users', load: () => import('./views/clubs.js') },
  sessions: { title: 'Занятия', icon: 'calendar', load: () => import('./views/sessions.js') },
  exceptions: { title: 'Изменения', icon: 'list', load: () => import('./views/exceptions.js') },
  reference: { title: 'Справочники', icon: 'book', load: () => import('./views/reference.js') },
  attendance: { title: 'Посещаемость', icon: 'list', hidden: true, load: () => import('./views/attendance.js') },
  account: { title: 'Аккаунт', icon: 'key', hidden: true, load: () => import('./views/account.js') },
};
const LOGIN = '/admin/login.html';
let admin;
let controller;
const main = document.querySelector('#admin-main');

// ADM-06: после входа вернёмся на тот же раздел (#/clubs и т.п.)
function toLogin() { location.replace(/^#\/[\w\-/]*$/.test(location.hash) ? `${LOGIN}?next=${encodeURIComponent(location.hash)}` : LOGIN); }
window.addEventListener('admin:unauthorized', toLogin);

function parseHash() {
  const [route = '', param = ''] = location.hash.replace(/^#\/?/, '').split('/');
  return { route: ROUTES[route] ? route : '', param };
}

function buildChrome() {
  const links = Object.entries(ROUTES).filter(([, r]) => !r.hidden);
  const nav = h('nav', { class: 'admin-nav', 'aria-label': 'Разделы админки' }, links.map(([key, r]) => h('a', { href: `#/${key}`, dataset: { route: key } }, r.title)));
  const bottom = h('nav', { class: 'bottom-nav', 'aria-label': 'Разделы админки (мобильная навигация)' },
    links.map(([key, r]) => h('a', { href: `#/${key}`, dataset: { route: key } }, h('span', { class: 'bn-pill' }, icon(r.icon)), h('span', { class: 'bn-label' }, r.title))));
  const slot = h('div', { class: 'admin-tools', dataset: { settingsSlot: '' } },
    h('a', { class: 'settings-button', href: '#/account', 'aria-label': `Аккаунт: ${admin.login}`, title: `Аккаунт: ${admin.login}`, dataset: { route: 'account' } }, icon('key')),
    h('button', { type: 'button', class: 'settings-button', 'aria-label': 'Выйти', title: 'Выйти', onclick: async () => { if (await guarded(logout)) toLogin(); } }, icon('logout')));
  document.querySelector('#admin-header').replaceChildren(
    h('a', { class: 'campus-brand', href: '/', 'aria-label': 'На сайт' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), h('span', {}, 'KipClub'), h('small', {}, 'Администрирование')), nav, slot);
  document.body.append(bottom);
}

function markCurrent(route) {
  for (const a of document.querySelectorAll('[data-route]')) {
    if (a.dataset.route === route) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
}

async function render() {
  const { route, param } = parseHash();
  controller?.abort();
  controller = new AbortController();
  const current = controller;
  markCurrent(route);
  document.title = `${ROUTES[route].title} — админка`;
  main.setAttribute('aria-busy', 'true');
  try {
    const view = await ROUTES[route].load();
    if (current.signal.aborted) return;
    await view.mount(main, { signal: current.signal, admin, param });
  } catch (error) {
    if (error?.name === 'AbortError' || current.signal.aborted) return;
    if (error?.status === 401) return; // уведомление admin:unauthorized уже перенаправило на вход
    main.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, error?.message || 'Не удалось загрузить раздел.'),
      h('button', { type: 'button', class: 'btn', onclick: render }, 'Повторить'));
  } finally { if (!current.signal.aborted) main.removeAttribute('aria-busy'); }
}

async function boot() {
  try {
    ({ admin } = await getAdminStatus());
  } catch (error) {
    if (error?.status === 401) { toLogin(); return; }
    main.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, error?.message || 'Сервер недоступен.'),
      h('button', { type: 'button', class: 'btn', onclick: () => location.reload() }, 'Повторить'));
    return;
  }
  buildChrome();
  window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); });
  await import('../settings.js'); // добавит кнопку настроек в [data-settings-slot]
  render();
}
boot();
