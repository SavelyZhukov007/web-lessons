import { getClubs, getCategories, getLeaders } from './api.js';
import { h, icon } from './ui.js';

const list = document.querySelector('#content');
const count = document.querySelector('#clubs-count');
const form = document.querySelector('#club-filters');
const search = document.querySelector('#club-search');
const category = document.querySelector('#club-category');
const reset = document.querySelector('#club-reset');
const lookup = { categories: new Map(), leaders: new Map() };

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

let seq = 0;
async function load() {
  const mine = ++seq;
  list.setAttribute('aria-busy', 'true');
  const filters = { search: search.value.trim(), category_id: category.value };
  reset.hidden = !(filters.search || filters.category_id);
  try {
    const clubs = await getClubs(filters);
    if (mine !== seq) return; // устаревший ответ
    count.textContent = `${clubs.length} ${plural(clubs.length)}`;
    if (!clubs.length) {
      list.replaceChildren(h('div', { class: 'empty-state' }, h('strong', {}, filters.search || filters.category_id ? 'Ничего не найдено' : 'Кружков пока нет'),
        filters.search || filters.category_id ? 'Попробуй изменить запрос или сбросить фильтры.' : 'Загляни позже — список появится здесь.'));
    } else list.replaceChildren(...clubs.map(card));
  } catch (error) {
    if (mine !== seq) return;
    count.textContent = '';
    list.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, h('p', {}, error.message), h('button', { type: 'button', class: 'btn btn--small', onclick: load }, 'Повторить попытку')));
  } finally {
    if (mine === seq) list.setAttribute('aria-busy', 'false');
  }
}

async function init() {
  const params = new URLSearchParams(location.search);
  search.value = params.get('search') || '';
  try {
    const [categories, leaders] = await Promise.all([getCategories(), getLeaders()]);
    for (const c of categories) { lookup.categories.set(c.id, c); category.append(h('option', { value: c.id }, c.name)); }
    for (const l of leaders) lookup.leaders.set(l.id, l);
    category.value = params.get('category_id') || '';
  } catch { /* фильтр по направлению недоступен, сам список всё равно загрузится */ }
  load();
}
let timer;
search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 250); });
category.addEventListener('change', load);
form.addEventListener('submit', event => { event.preventDefault(); load(); });
reset.addEventListener('click', () => { search.value = ''; category.value = ''; load(); search.focus(); });
init();
