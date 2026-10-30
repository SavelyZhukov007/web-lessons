// Диалог «Обратная связь» (сайт, PWA, Android — один UI): тип, описание, контакт, скриншоты; журнал устройства прикладывается всегда.
// Отправка: POST /api/feedback (multipart). Открывается из «Настроек» (js/settings.js).
import { h, icon, toast } from './ui.js';
import { request } from './api.js';
import { install, deviceInfo } from './log-collector.js';

import { TYPES, DESC_MAX, MAX_SHOTS, MIME, validate, buildFormData } from './feedback-logic.js';

let dialog;

export function openFeedback(opener) {
  const logs = install(window);
  const state = { type: 'bug', files: [], sending: false };
  dialog?.remove();
  dialog = h('dialog', { class: 'sheet sheet--bottom feedback-sheet', 'aria-labelledby': 'feedback-title' });
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => opener?.focus?.());
  const err = name => h('p', { class: 'field-error', role: 'alert', hidden: true, dataset: { err: name } });
  const errors = { type: err('type'), description: err('description'), contact: err('contact'), files: err('files') };

  const typeGroup = h('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Тип обращения' },
    TYPES.map(([v, t]) => {
      const input = h('input', { type: 'radio', name: 'fb-type', value: v, checked: v === state.type });
      input.addEventListener('change', () => { state.type = v; });
      return h('label', {}, input, h('span', {}, t));
    }));
  const desc = h('textarea', { id: 'fb-desc', rows: 5, maxlength: DESC_MAX, required: true, placeholder: 'Что произошло или что хотелось бы улучшить?' });
  const counter = h('span', { class: 'fb-counter', 'aria-live': 'off' }, `0 / ${DESC_MAX}`);
  desc.addEventListener('input', () => { counter.textContent = `${desc.value.length} / ${DESC_MAX}`; if (!errors.description.hidden) check(); });
  const contact = h('input', { id: 'fb-contact', type: 'text', maxlength: 100, autocomplete: 'email', placeholder: 'e-mail или @telegram' });
  const honeypot = h('input', { type: 'text', name: 'website', tabindex: '-1', autocomplete: 'off', class: 'fb-hp', 'aria-hidden': 'true' });

  const thumbs = h('div', { class: 'fb-thumbs' });
  const picker = h('input', { type: 'file', accept: MIME.join(','), multiple: true, hidden: true });
  const addBtn = h('button', { type: 'button', class: 'btn btn--small btn--tonal' }, icon('plus'), ' Скриншот');
  addBtn.addEventListener('click', () => picker.click());
  const renderThumbs = () => {
    thumbs.replaceChildren(...state.files.map((f, i) => h('figure', { class: 'fb-thumb' }, f.url ? h('img', { src: f.url, alt: `Скриншот ${i + 1}` }) : h('span', { class: 'fb-thumb-name' }, f.file.name),
      h('button', { type: 'button', class: 'fb-thumb-remove', 'aria-label': `Убрать скриншот ${i + 1}`, onclick: () => { state.files.splice(i, 1); renderThumbs(); check(); } }, icon('close')))));
    addBtn.disabled = state.files.length >= MAX_SHOTS;
  };
  picker.addEventListener('change', () => {
    const picked = [...picker.files];
    picker.value = '';
    Promise.all(picked.map(file => new Promise(resolve => {
      const entry = { file, type: file.type, size: file.size, url: '' };
      if (!file.type.startsWith('image/') || file.size > 5 * 1024 * 1024) return resolve(entry);
      const reader = new FileReader();
      reader.onload = () => { entry.url = String(reader.result); resolve(entry); };
      reader.onerror = () => resolve(entry);
      reader.readAsDataURL(file);
    }))).then(entries => { state.files.push(...entries); renderThumbs(); check(); });
  });

  let info = null;
  const status = h('div', { class: 'fb-status', role: 'status' });
  const submit = h('button', { type: 'submit', class: 'btn btn--filled' }, 'Отправить');
  const cancel = h('button', { type: 'button', class: 'btn btn--text', onclick: () => dialog.close() }, 'Отмена');

  function check() {
    const found = validate({ type: state.type, description: desc.value, contact: contact.value, files: state.files });
    for (const [k, el] of Object.entries(errors)) { el.textContent = found[k] || ''; el.hidden = !found[k]; }
    desc.setAttribute('aria-invalid', String(!!found.description)); contact.setAttribute('aria-invalid', String(!!found.contact));
    return found;
  }

  async function send() {
    if (state.sending) return;
    const found = check();
    if (Object.keys(found).length) { (found.description ? desc : found.contact ? contact : addBtn).focus(); return; }
    state.sending = true; submit.disabled = true; status.className = 'fb-status'; status.textContent = 'Отправляю…';
    try {
      if (!info) info = await deviceInfo(window);
      const fd = buildFormData({ type: state.type, description: desc.value, contact: contact.value, website: honeypot.value, info, logs: logs.entries(), files: state.files });
      await request('/api/feedback', { method: 'POST', body: fd, timeout: 60000 });
      form.replaceChildren(h('div', { class: 'fb-success' }, h('h3', {}, 'Спасибо!'), h('p', {}, 'Сообщение отправлено. Мы обязательно его прочитаем.'),
        h('button', { type: 'button', class: 'btn btn--filled', onclick: () => dialog.close() }, 'Готово')));
      toast('Обратная связь отправлена');
    } catch (e) {
      const offline = navigator.onLine === false;
      status.className = 'fb-status fb-status--error';
      status.replaceChildren(h('span', {}, offline ? 'Нет подключения к интернету.' : (e?.message || 'Не удалось отправить.')), ' ',
        h('button', { type: 'button', class: 'btn btn--small', onclick: send }, 'Повторить'));
    } finally { state.sending = false; submit.disabled = false; }
  }

  const form = h('form', { class: 'sheet-body fb-form', novalidate: true },
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Тип'), typeGroup, errors.type),
    h('label', { class: 'field', for: 'fb-desc' }, h('span', { class: 'field-label' }, 'Описание'), desc, h('span', { class: 'fb-under' }, errors.description, counter)),
    h('label', { class: 'field', for: 'fb-contact' }, h('span', { class: 'field-label' }, 'Контакт для ответа (необязательно)'), contact, errors.contact),
    honeypot,
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Скриншоты'), thumbs, picker, addBtn, errors.files),
    status, h('p', { class: 'fb-tech' }, 'К обращению автоматически прикладываются технические данные (версия, устройство, журнал ошибок) — без паролей и личных данных.'),
    h('div', { class: 'sheet-foot' }, cancel, submit));
  form.addEventListener('submit', e => { e.preventDefault(); send(); });
  contact.addEventListener('blur', () => { if (contact.value) check(); });

  dialog.append(h('div', { class: 'sheet-head sheet-head--center' }, h('span', { 'aria-hidden': 'true' }), h('h2', { id: 'feedback-title' }, 'Обратная связь'),
    h('button', { type: 'button', class: 'btn btn--text btn--small', 'aria-label': 'Закрыть', onclick: () => dialog.close() }, icon('close'))), form);
  document.body.append(dialog);
  renderThumbs();
  dialog.showModal();
  desc.focus();
}
