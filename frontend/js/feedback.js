// Диалог «Обратная связь» (сайт, PWA, Android, один UI): тип, оценка, описание, контакт (необязательно), скриншоты.
// Журнал устройства и техданные прикладываются всегда. Отправка: POST /api/feedback (multipart).
// Открывается из «Настроек», карточки «Как тебе KipClub?», «Что нового», экранов ошибки и офлайна, встряхиванием в APK.
import { h, icon, toast } from './ui.js';
import { request } from './api.js';
import { install, deviceInfo } from './log-collector.js';

import { TYPES, DESC_MAX, MAX_SHOTS, MIME, RATINGS, SOURCES, validate, buildFormData } from './feedback-logic.js';
import { load as loadPrompt, save as savePrompt, sent as promptSent } from './feedback-prompt-logic.js';

let dialog;

export function openFeedback(opener, { type = 'bug', rating = '', source = 'settings' } = {}) {
  const logs = install(window);
  source = SOURCES.includes(source) ? source : 'settings';
  const state = { type: TYPES.some(([v]) => v === type) ? type : 'bug', rating: /^[1-5]$/.test(String(rating)) ? String(rating) : '', files: [], sending: false };
  window.KipUsage?.emit('fb_form_open', source);
  dialog?.remove();
  dialog = h('dialog', { class: 'sheet sheet--bottom feedback-sheet', 'aria-labelledby': 'feedback-title' });
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { state.files.forEach(f => { if (f.url) URL.revokeObjectURL(f.url); }); opener?.focus?.(); });
  const err = name => h('p', { class: 'field-error', role: 'alert', hidden: true, dataset: { err: name } });
  const errors = { type: err('type'), description: err('description'), contact: err('contact'), files: err('files') };

  const typeGroup = h('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Тип сообщения' },
    TYPES.map(([v, t]) => {
      const input = h('input', { type: 'radio', name: 'fb-type', value: v, checked: v === state.type });
      input.addEventListener('change', () => { state.type = v; });
      return h('label', {}, input, h('span', {}, t));
    }));
  const desc = h('textarea', { id: 'fb-desc', rows: 5, maxlength: DESC_MAX, required: true, placeholder: 'Что произошло или что хотелось бы улучшить?' });
  const counter = h('span', { class: 'fb-counter', 'aria-live': 'off' }, `0 / ${DESC_MAX}`);
  desc.addEventListener('input', () => { counter.textContent = `${desc.value.length} / ${DESC_MAX}`; if (!errors.description.hidden) check(); });
  const ratingGroup = h('div', { class: 'fb-rating', role: 'radiogroup', 'aria-label': 'Оценка, необязательно' },
    RATINGS.map(([v, face, label]) => {
      const input = h('input', { type: 'radio', name: 'fb-rating', value: v, checked: v === state.rating, 'aria-label': label });
      input.addEventListener('click', () => { state.rating = state.rating === v ? '' : v; input.checked = !!state.rating; });
      return h('label', { title: label }, input, h('span', { 'aria-hidden': 'true' }, face));
    }));
  const contact = h('input', { id: 'fb-contact', type: 'text', maxlength: 100, autocomplete: 'email', placeholder: 'e-mail или @telegram', 'aria-describedby': 'fb-contact-hint' });
  const honeypot = h('input', { type: 'text', name: 'website', tabindex: '-1', autocomplete: 'off', class: 'fb-hp', 'aria-hidden': 'true' });

  const thumbs = h('div', { class: 'fb-thumbs' });
  const picker = h('input', { type: 'file', accept: MIME.join(','), multiple: true, hidden: true });
  const addBtn = h('button', { type: 'button', class: 'btn btn--small btn--tonal' }, icon('plus'), ' Скриншот');
  addBtn.addEventListener('click', () => picker.click());
  const fmtSize = n => n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(n / 1024))} КБ`;
  const revoke = f => { if (f.url) { URL.revokeObjectURL(f.url); f.url = ''; } };
  const removeShot = i => { const [f] = state.files.splice(i, 1); if (f) revoke(f); renderThumbs(); check(); };
  const renderThumbs = () => {
    thumbs.replaceChildren(...state.files.map((f, i) => {
      const fig = h('figure', { class: 'fb-thumb', title: `${f.file.name} · ${fmtSize(f.size)}` });
      if (f.url) {
        const img = h('img', { src: f.url, alt: `Скриншот ${i + 1}`, decoding: 'async' });
        img.addEventListener('error', () => { fig.classList.add('fb-thumb--noimg'); img.remove(); });
        fig.append(img);
      } else fig.classList.add('fb-thumb--noimg');
      fig.append(h('figcaption', { class: 'fb-thumb-caption' }, h('span', { class: 'fb-thumb-name' }, f.file.name), h('span', { class: 'fb-thumb-size' }, fmtSize(f.size))),
        h('button', { type: 'button', class: 'fb-thumb-remove', 'aria-label': `Убрать скриншот ${i + 1}`, onclick: () => removeShot(i) }, icon('close')));
      return fig;
    }));
    addBtn.disabled = state.files.length >= MAX_SHOTS;
  };
  picker.addEventListener('change', () => {
    const picked = [...picker.files];
    picker.value = '';
    // Превью через object URL (быстрее data URL, без чтения файла в память); освобождается при удалении/закрытии.
    const entries = picked.map(file => ({ file, type: file.type, size: file.size,
      url: (!file.type || file.type.startsWith('image/')) ? URL.createObjectURL(file) : '' }));
    state.files.push(...entries); renderThumbs(); check();
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
      const fd = buildFormData({ type: state.type, description: desc.value, contact: contact.value, website: honeypot.value, info, logs: logs.entries(), files: state.files,
        rating: state.rating, source });
      await request('/api/feedback', { method: 'POST', body: fd, timeout: 60000 });
      window.KipUsage?.emit('fb_sent', source);
      try { savePrompt(localStorage, promptSent(loadPrompt(localStorage), Date.now())); } catch { /* storage недоступен */ }
      form.replaceChildren(h('div', { class: 'fb-success' }, h('p', {}, 'Сообщение отправлено. Спасибо!'),
        h('button', { type: 'button', class: 'btn btn--filled', onclick: () => dialog.close() }, 'Готово')));
      toast('Сообщение отправлено');
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
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Оценка ', h('span', { class: 'fb-optional' }, 'необязательно')), ratingGroup),
    h('label', { class: 'field', for: 'fb-contact' }, h('span', { class: 'field-label' }, 'Контакт для ответа ', h('span', { class: 'fb-optional' }, 'необязательно')), contact,
      h('span', { class: 'field-hint', id: 'fb-contact-hint' }, 'Оставь, только если хочешь, чтобы мы ответили. Без контакта сообщение тоже дойдёт.'), errors.contact),
    honeypot,
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Скриншоты'), thumbs, picker, h('div', { class: 'fb-shots-row' }, addBtn, h('span', { class: 'fb-hint' }, 'Один скриншот до 5 МБ')), errors.files),
    status, h('p', { class: 'fb-tech' }, 'Вместе с сообщением мы получим технические данные: версию, модель устройства и журнал ошибок. Паролей и личных данных там нет.'),
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
