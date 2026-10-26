import { getClubs, getCategories, getLeaders } from './api.js';
import { h, icon } from './ui.js';
import { readClubFilters, buildClubUrl } from './club-filters.js';
import { latestRequest } from './latest-request.js';

const list = document.querySelector('#content');
const count = document.querySelector('#clubs-count');
const form = document.querySelector('#club-filters');
const search = document.querySelector('#club-search');
const category = document.querySelector('#club-category');
const reset = document.querySelector('#club-reset');
const lookup = { categories: new Map(), leaders: new Map() };
const referenceStatus = h('div', { 'aria-live': 'polite' });
form.after(referenceStatus);

const plural = n => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? 'кружок' : [2, 3, 4].includes(m10) && ![12, 13, 14].includes(m100) ? 'кружка' : 'кружков';
};
const safeColor = c => (/^#[\da-f]{6}$/i.test(c) ? c : '');

function card(club) {
  const cat = lookup.categories.get(club.category_id);
  const leader = lookup.leaders.get(club.leader_id);
  const dot = h('span', { class: 'dot', 'aria-hidden': 'true' });
  const color = safeColor(cat?.color);
  if (color) dot.style.setProperty('--dot', color);
  return h('a', { class: 'club-card', href: `/club.html?id=${club.id}` },
    h('h2', {}, club.name),
    h('p', {}, club.description || 'Описание пока не добавлено.'),
    h('div', { class: 'club-meta' }, dot, cat ? h('span', {}, cat.name) : null, leader ? h('span', {}, `· ${leader.name}`) : null, h('span', { class: 'club-arrow' }, icon('arrow'))));
}

const clubsRequest = latestRequest();
async function load() {
  clearTimeout(timer);
  const request = clubsRequest.begin();
  list.setAttribute('aria-busy', 'true');
  const filters = { search: search.value.trim(), category_id: category.value };
  const nextUrl = buildClubUrl(location.href, filters);
  if (nextUrl !== location.pathname + location.search + location.hash) history.replaceState(history.state, '', nextUrl);
  reset.hidden = !(filters.search || filters.category_id);
  try {
    const clubs = await getClubs(filters, { signal: request.signal });
    if (!request.isCurrent()) return;
    count.textContent = `${clubs.length} ${plural(clubs.length)}`;
    if (!clubs.length) {
      list.replaceChildren(h('div', { class: 'empty-state' }, h('strong', {}, filters.search || filters.category_id ? 'Ничего не найдено' : 'Кружков пока нет'),
        filters.search || filters.category_id ? 'Попробуй изменить запрос или сбросить фильтры.' : 'Загляни позже — список появится здесь.'));
    } else list.replaceChildren(...clubs.map(card));
  } catch (error) {
    if (!request.isCurrent()) return;
    count.textContent = '';
    list.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, h('p', {}, error.message), h('button', { type: 'button', class: 'btn btn--small', onclick: load }, 'Повторить попытку')));
  } finally {
    if (request.isCurrent()) list.setAttribute('aria-busy', 'false');
  }
}

async function init() {
  const params = readClubFilters(location.search);
  search.value = params.search;
  await loadReferences(params.category_id);
}
async function loadReferences(selected = category.value) {
  category.disabled = true;
  const results = await Promise.allSettled([getCategories(), getLeaders()]);
  referenceStatus.replaceChildren();
  if (results[0].status === 'fulfilled') {
    lookup.categories.clear();
    category.replaceChildren(h('option', { value: '' }, 'Все направления'));
    for (const c of results[0].value) { lookup.categories.set(c.id, c); category.append(h('option', { value: c.id }, c.name)); }
    category.value = selected;
    if (category.selectedIndex === -1) category.value = '';
    category.disabled = false;
  } else if (selected) {
    category.replaceChildren(h('option', { value: '' }, 'Все направления'), h('option', { value: selected }, `Выбранное направление № ${selected}`));
    category.value = selected;
  }
  if (results[1].status === 'fulfilled') {
    lookup.leaders.clear();
    for (const l of results[1].value) lookup.leaders.set(l.id, l);
  }
  if (results.some(r => r.status === 'rejected')) referenceStatus.append(
    h('p', {}, 'Часть справочников не загрузилась. Список кружков доступен.'),
    h('button', { type: 'button', class: 'btn btn--small', onclick: () => loadReferences() }, 'Повторить загрузку справочников'));
  await load();
}
let timer;
search.addEventListener('input', () => { clubsRequest.cancel(); clearTimeout(timer); timer = setTimeout(load, 250); });
category.addEventListener('change', load);
form.addEventListener('submit', event => { event.preventDefault(); load(); });
reset.addEventListener('click', () => { search.value = ''; category.value = ''; load(); search.focus(); });
init();
