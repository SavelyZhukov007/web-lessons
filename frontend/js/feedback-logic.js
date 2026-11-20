// Чистая логика формы «Обратная связь» (проверка, сборка FormData), без DOM, покрыта frontend/tests/feedback-logic.test.mjs.
'use strict';

export const TYPES = [['idea', 'Идея'], ['bug', 'Ошибка'], ['question', 'Вопрос'], ['other', 'Другое']];
export const DESC_MIN = 10, DESC_MAX = 2000, MAX_SHOTS = 5, MAX_SHOT = 5 * 1024 * 1024;
export const MIME = ['image/png', 'image/jpeg', 'image/webp'];
export const SOURCES = ['settings', 'prompt_usage', 'prompt_update', 'prompt_error', 'whats_new', 'shake', 'offline', 'error'];
export const RATINGS = [['1', '😞', 'очень плохо'], ['2', '🙁', 'плохо'], ['3', '😐', 'нормально'], ['4', '🙂', 'хорошо'], ['5', '😍', 'отлично']];
const CONTACT = /^([^@\s]{1,64}@[^@\s]{1,100}\.[A-Za-z]{2,}|@?[A-Za-z0-9_]{4,32}|(https?:\/\/)?t\.me\/[A-Za-z0-9_]{4,32})$/;

export function validate({ type, description, contact, files }) {
  const errors = {};
  if (!TYPES.some(([v]) => v === type)) errors.type = 'Выбери тип сообщения';
  const len = description.trim().length;
  if (len < DESC_MIN) errors.description = `Напиши чуть подробнее, хотя бы ${DESC_MIN} символов`;
  else if (len > DESC_MAX) errors.description = `Не больше ${DESC_MAX} символов`;
  if (contact.trim() && !CONTACT.test(contact.trim())) errors.contact = 'E-mail или Telegram (@username)';
  if (files.length > MAX_SHOTS) errors.files = `Не больше ${MAX_SHOTS} скриншотов`;
  else if (files.some(f => !MIME.includes(f.type))) errors.files = 'Только PNG, JPEG или WebP';
  else if (files.some(f => f.size > MAX_SHOT)) errors.files = 'Один скриншот до 5 МБ';
  return errors;
}

// Технические данные (версия, устройство, журнал) прикладываются ВСЕГДА, отключить нельзя.
// rating (1..5) приходит из карточки «Как тебе KipClub?» или из формы, source: откуда открыта форма.
export function buildFormData({ type, description, contact = '', website = '', info = {}, logs = [], files = [], rating = '', source = 'settings' }, FD = FormData) {
  const fd = new FD();
  fd.set('type', type); fd.set('description', description.trim()); fd.set('contact', contact.trim()); fd.set('website', website);
  if (/^[1-5]$/.test(String(rating))) fd.set('rating', String(rating));
  fd.set('source', SOURCES.includes(source) ? source : 'settings');
  fd.set('meta', JSON.stringify(info));
  fd.set('logs', JSON.stringify(Array.isArray(logs) ? logs : []));
  files.forEach((f, i) => fd.append('screenshots', f.file, `${String(i + 1).padStart(2, '0')}.${f.type.split('/')[1]}`));
  return fd;
}
