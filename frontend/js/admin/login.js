import {login} from './api.js';
document.querySelector('#login-form').addEventListener('submit', event => {
  event.preventDefault();
  try { login(); } catch (error) { document.querySelector('#message').textContent = error.message; }
});
