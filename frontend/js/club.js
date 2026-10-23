import { getClub } from './api.js';

const content = document.querySelector('#content');
const heading = document.querySelector('#club-name');
const id = Number(new URLSearchParams(location.search).get('id'));

async function load() {
  content.setAttribute('aria-busy', 'true');
  try {
    const club = await getClub(id);
    heading.textContent = club.name;
    document.title = `${club.name} — кружки.`;
    const description = document.createElement('p');
    description.className = 'detail-copy';
    description.textContent = club.description || 'Описание кружка пока не добавлено.';
    content.replaceChildren(description);
  } catch (error) {
    if (error.status === 404) heading.textContent = 'Кружок не найден';
    const message = document.createElement('p');
    message.className = 'detail-copy';
    message.textContent = error.message;
    content.replaceChildren(message);
    if (error.status !== 404) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Повторить попытку';
      retry.addEventListener('click', load);
      content.append(retry);
    }
  } finally {
    content.setAttribute('aria-busy', 'false');
  }
}
load();
