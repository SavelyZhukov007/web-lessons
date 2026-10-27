import { login, getAdminStatus } from './api.js';

const form = document.querySelector('#login-form');
const message = document.querySelector('#message');
const submit = form.querySelector('button[type=submit]');
// ADM-06: ?next=#/раздел — вернуть на страницу, с которой выбросило по истёкшей сессии (только внутренние хэш-маршруты)
const rawNext = new URLSearchParams(location.search).get('next') || '';
const ADMIN_PAGE = '/admin/index.html' + (/^#\/[\w\-/]*$/.test(rawNext) ? rawNext : '');

// Уже вошёл — сразу в админку.
getAdminStatus().then(status => {
  if (window.ItcSession && window.ItcSession.role() !== 'admin') window.ItcSession.set('admin', status.admin?.login || 'Администратор');
  location.replace(ADMIN_PAGE);
}, () => {});

function show(text, isError) {
  message.textContent = text;
  message.className = isError ? 'field-error' : 'field-hint';
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const loginName = form.elements.login.value.trim();
  const password = form.elements.password.value;
  if (!loginName || !password) { show('Введи логин и пароль.', true); return; }
  submit.disabled = true;
  show('Выполняется вход…', false);
  try {
    await login(loginName, password);
    location.assign(ADMIN_PAGE);
  } catch (error) {
    form.elements.password.value = '';
    form.elements.password.focus();
    show(error.status === 401 ? 'Неверный логин или пароль.' : error.message, true);
    submit.disabled = false;
  }
});
