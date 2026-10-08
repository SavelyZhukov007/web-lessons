import {getClub} from './api.js';
const content = document.querySelector('#content');
const id = Number(new URLSearchParams(location.search).get('id'));
try {
  const club = await getClub(id);
  if (!club) content.textContent = 'Кружок не найден';
  else {
    const title = document.createElement('h2'); title.textContent = club.name;
    const description = document.createElement('p'); description.textContent = club.description;
    content.append(title, description);
  }
} catch (error) { content.textContent = error.message; }
