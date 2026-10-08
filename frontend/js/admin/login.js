import {login} from './api.js';
// TODO: форма логина и пароля; серверная сессия, не localStorage-флаг.
document.querySelector('#login-form').addEventListener('submit', event => {
  event.preventDefault();
  try { login(); } catch (error) { document.querySelector('#message').textContent = error.message; }
});
