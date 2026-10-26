import { h } from '../../ui.js';
import { changePassword, logout } from '../api.js';
import { pageHeader, formDialog, guarded } from '../kit.js';
import { toast } from '../../ui.js';

export async function openChangePassword() {
  {
    const done = await formDialog({
      title: 'Смена пароля', submitLabel: 'Сменить пароль',
      intro: 'Минимум 10 символов, не совпадает с логином и не из списка простых паролей. Остальные сессии будут завершены.',
      fields: [
        { name: 'current_password', label: 'Текущий пароль', type: 'password', required: true },
        { name: 'new_password', label: 'Новый пароль', type: 'password', required: true, hint: 'Лучше фраза из нескольких слов.' },
        { name: 'repeat', label: 'Повтори новый пароль', type: 'password', required: true },
      ],
      onSubmit: values => {
        if (values.new_password !== values.repeat) throw new Error('Новые пароли не совпадают.');
        return changePassword(values.current_password, values.new_password);
      },
    });
    if (done) toast('Пароль изменён');
    return done;
  }
}

export async function mount(root, { admin, param }) {
  const change = openChangePassword;
  root.replaceChildren(
    pageHeader('Аккаунт'),
    h('section', { class: 'card account-card' },
      h('dl', { class: 'facts' }, h('dt', {}, 'Логин'), h('dd', {}, admin.login)),
      h('div', { class: 'form-actions' },
        h('button', { type: 'button', class: 'btn', onclick: change }, 'Сменить пароль'),
        h('button', { type: 'button', class: 'btn btn--outline-danger', onclick: async () => { if (await guarded(logout)) location.assign('/admin/login.html'); } }, 'Выйти'))));
  root.querySelector('#view-title').focus({ preventScroll: true });
  if (param === 'password') change(); // из «Настроек» приложения: #/account/password
}
