import {getClubs} from './api.js';
const list = document.querySelector('#content');
try {
  for (const club of await getClubs()) {
    const link = document.createElement('a');
    link.href = `/club.html?id=${club.id}`;
    link.textContent = club.name;
    list.append(link);
  }
} catch (error) { list.textContent = error.message; }
