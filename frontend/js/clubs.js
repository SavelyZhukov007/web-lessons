import { getClubs } from './api.js';
import { icon } from './icons.js';

const list = document.querySelector('#content');
async function load() {
  list.setAttribute('aria-busy', 'true');
  try {
    const clubs = await getClubs();
    list.replaceChildren();
    if (clubs.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'directory-copy';
      empty.textContent = 'Активных кружков пока нет.';
      list.append(empty);
    }
    for (const club of clubs) {
      const link = document.createElement('a');
      link.href = `/club.html?id=${club.id}`;
      const name = document.createElement('span');
      name.textContent = club.name;
      link.append(name, icon('arrow'));
      list.append(link);
    }
  } catch (error) {
    const message = document.createElement('p');
    message.className = 'directory-copy';
    message.textContent = error.message;
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = 'Повторить попытку';
    retry.addEventListener('click', load);
    list.replaceChildren(message, retry);
  } finally {
    list.setAttribute('aria-busy', 'false');
  }
}
load();
