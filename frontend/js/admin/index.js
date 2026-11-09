// Оболочка админки: проверка сессии, шапка/навигация, hash-роутер (#/clubs, #/reference/rooms …), перенаправление на вход при 401.
import { h, icon } from '../ui.js';
import { exceptions, getAdminStatus, logout } from './api.js';
import { guarded } from './kit.js';
import { dateKey, moscowToday } from '../schedule-dates.js';
import { bindGlassIndicator, mountGlassEverywhere, mountGlassOptics } from '../glass.js';

const ROUTES = {
  '': { title: 'Обзор', icon: 'home', load: () => import('./views/dashboard.js') },
  clubs: { title: 'Кружки', icon: 'users', load: () => import('./views/clubs.js') },
  sessions: { title: 'Занятия', icon: 'calendar', load: () => import('./views/sessions.js') },
  periods: { title: 'Учебные периоды', hidden: true, icon: 'calendar', load: () => import('./views/periods.js') },
  imports: { title: 'Импорт расписания', hidden: true, icon: 'calendar', load: () => import('./views/imports.js') },
  exceptions: { title: 'Изменения', mobileTitle: 'Правки', icon: 'list', load: () => import('./views/exceptions.js') },
  reference: { title: 'Справочники', mobileTitle: 'Данные', icon: 'book', load: () => import('./views/reference.js') },
  broadcasts: { title: 'Рассылки', mobileTitle: 'Анонсы', icon: 'megaphone', load: () => import('./views/broadcasts.js') },
  calendar: { title: 'Календарь переносов', hidden: true, icon: 'calendar', load: () => import('./views/calendar.js') },
  bulk: { title: 'Пакетные изменения', hidden: true, icon: 'list', load: () => import('./views/bulk.js') },
  export: { title: 'Экспорт и печать', hidden: true, icon: 'list', load: () => import('./views/export.js') },
  actions: { title: 'Журнал действий', hidden: true, icon: 'list', load: () => import('./views/actions.js') },
  account: { title: 'Аккаунт', icon: 'key', hidden: true, load: () => import('./views/account.js') },
};
const LOGIN = '/admin/login.html';
let admin;
let controller;
let updateBottomIndicator;
let changesKnown = false;
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
  const bottom = h('nav', { class: 'bottom-nav glass-tabs glass-surface', 'aria-label': 'Разделы админки (мобильная навигация)' },
    links.map(([key, r]) => h('a', { href: `#/${key}`, 'aria-label': r.title, dataset: { route: key } }, h('span', { class: 'bn-pill' }, icon(r.icon)), h('span', { class: 'bn-label' }, r.mobileTitle || r.title))));
  // «Сменить пароль» и «Выйти» — в «Настройках» (шестерёнка), см. js/settings.js → window.ClubsAdmin
  const slot = h('div', { class: 'admin-tools', dataset: { settingsSlot: '' } });
  window.ClubsAdmin = {
    login: admin.login,
    changePassword: async () => (await import('./views/account.js')).openChangePassword(),
    logout: async () => { if (await guarded(logout)) toLogin(); },
  };
  document.querySelector('#admin-header').replaceChildren(
    h('a', { class: 'campus-brand', href: '/', 'aria-label': 'На сайт' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), h('span', {}, 'KipClub'), h('small', {}, 'Администрирование')), nav, slot);
  document.body.append(bottom);
  updateBottomIndicator = bindGlassIndicator(bottom, () => bottom.querySelector('[aria-current="page"]'));
  mountGlassOptics(bottom);
  mountGlassEverywhere();
  const changeLinks = [nav, bottom].map(element => element.querySelector('[data-route="exceptions"]'));
  const badges = changeLinks.map(link => {
    const badge = h('span', { class: 'admin-change-count', hidden: true, 'aria-hidden': 'true' });
    (link.querySelector('.bn-pill') || link).append(badge);
    return badge;
  });
  window.addEventListener('admin:schedule-changes', ({ detail }) => {
    if (!Array.isArray(detail)) return;
    changesKnown = true;
    const today = dateKey(moscowToday());
    const count = detail.filter(item => item.original_date >= today || item.new_date >= today).length;
    badges.forEach((badge, index) => {
      badge.hidden = !count;
      badge.textContent = count > 99 ? '99+' : String(count);
      changeLinks[index].setAttribute('aria-label', count ? `Изменения, предстоящих: ${count}` : 'Изменения');
    });
  });
  // Высота зависит от переноса подписей и размера шрифта, а не от фиксированных 72px.
  if ('ResizeObserver' in window) new ResizeObserver(() => {
    document.body.style.setProperty('--bottom-nav-h', `${bottom.getBoundingClientRect().height}px`);
  }).observe(bottom);
}

function markCurrent(route) {
  for (const a of document.querySelectorAll('[data-route]')) {
    if (a.dataset.route === route) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  updateBottomIndicator();
}

async function render() {
  const { route, param } = parseHash();
  controller?.abort();
  controller = new AbortController();
  const current = controller;
  main.dataset.adminTool = ['actions', 'bulk', 'export', 'calendar'].includes(route) ? '1' : '0';
  markCurrent(['bulk', 'export', 'calendar'].includes(route) ? 'sessions' : route === 'actions' ? '' : route);
  document.title = `${ROUTES[route].title} — админка`;
  main.setAttribute('aria-busy', 'true');
  try {
    const view = await ROUTES[route].load();
    if (current.signal.aborted) return;
    await view.mount(main, { signal: current.signal, admin, param });
    if (!changesKnown && !current.signal.aborted) exceptions.list({ signal: current.signal }).catch(() => {});
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
  const { mountQuickTools } = await import('./quick-tools.js');
  mountQuickTools(ROUTES, document.querySelector('.admin-tools'), render);
  window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); });
  await import('../settings.js'); // добавит кнопку настроек в [data-settings-slot]
  render();
}
boot();
