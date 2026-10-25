// Диалог «Настройки»: тема, акцент, размер текста, «Объявления» (если в браузере включены уведомления) (+ адрес сервера в Android-приложении).
// Подключается на каждой странице: <script type="module" src="/js/settings.js">. Кнопка-шестерёнка добавляется в шапку сама.
import { h, icon, toast, installRipple } from './ui.js';
import { request } from './api.js';

const theme = window.ClubsTheme;
const THEMES = [['system', 'Системная'], ['light', 'Светлая'], ['dark', 'Тёмная']];
const ACCENTS = [['brick', 'Кирпичный'], ['blue', 'Синий'], ['green', 'Зелёный'], ['violet', 'Фиолетовый']];
const SIZES = [['normal', 'Обычный'], ['large', 'Крупный'], ['xlarge', 'Очень крупный']];

let dialog;

function radioGroup(name, label, options, current, onPick, extra = '') {
  const group = h('div', { class: `segmented ${extra}`.trim(), role: 'radiogroup', 'aria-label': label });
  for (const [value, text] of options) {
    const input = h('input', { type: 'radio', name, value, checked: value === current });
    input.addEventListener('change', () => onPick(value));
    group.append(h('label', {}, input, h('span', {}, text)));
  }
  return group;
}

function swatches(current, onPick) {
  const wrap = h('div', { class: 'swatches', role: 'radiogroup', 'aria-label': 'Акцентный цвет' });
  for (const [value, text] of ACCENTS) {
    const input = h('input', { type: 'radio', name: 'accent', value, checked: value === current, 'aria-label': text });
    input.addEventListener('change', () => onPick(value));
    wrap.append(h('label', { class: 'swatch', title: text, dataset: { accent: value } }, input, h('span', {})));
  }
  return wrap;
}

function serverSection() {
  const S = window.AppServer;
  if (!S || S.fixed) return null; // публичная сборка APK: сервер зашит, менять нельзя
  const input = h('input', { type: 'url', id: 'settings-server', value: S.get(), inputmode: 'url', autocomplete: 'off', placeholder: 'http://192.168.1.50:8000' });
  const status = h('p', { class: 'field-hint', role: 'status' }, S.get() ? `Текущий сервер: ${S.get()}` : 'Сервер не задан.');
  const test = h('button', { type: 'button', class: 'btn btn--small' }, 'Проверить');
  const save = h('button', { type: 'button', class: 'btn btn--small btn--filled' }, 'Сохранить');
  const busy = value => { test.disabled = save.disabled = value; };
  test.addEventListener('click', async () => {
    busy(true); status.textContent = 'Проверяю соединение…';
    try { const r = await S.test(input.value); status.textContent = `Сервер отвечает ✔ ${r.base} (кружков: ${r.clubs})`; }
    catch (e) { status.textContent = e.message; } finally { busy(false); }
  });
  save.addEventListener('click', async () => {
    busy(true);
    try { const r = await S.test(input.value); S.set(r.base); location.reload(); }
    catch (e) { status.textContent = `${e.message} (адрес не сохранён)`; busy(false); }
  });
  return h('section', { class: 'sheet-section' }, h('h3', {}, 'Сервер'),
    h('div', { class: 'form-grid' }, h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Адрес сервера'), input), status,
      h('div', { class: 'form-actions' }, test, save)));
}

// «Объявления от администрации» для этого браузера. Видно, только если уже есть push-подписка (на кружок или «Мои кружки»).
// В приложении Android свой переключатель — в его настройках.
function announcementsSection() {
  if (window.Capacitor?.isNativePlatform?.() || !('serviceWorker' in navigator) || !('PushManager' in window)) return null;
  const box = h('input', { type: 'checkbox', id: 'settings-announcements' });
  const section = h('section', { class: 'sheet-section', hidden: true, dataset: { announcementsSection: '' } }, h('h3', {}, 'Уведомления'),
    h('label', { class: 'checkbox', for: 'settings-announcements' }, box, 'Объявления'),
    h('p', { class: 'field-hint' }, 'Важные сообщения от администрации. Уведомления об отменах и переносах не отключаются.'));
  const post = (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let endpoint;
  navigator.serviceWorker.getRegistration('/').then(reg => reg?.pushManager.getSubscription()).then(async sub => {
    if (!sub) return;
    endpoint = sub.endpoint;
    const st = await post('/api/push/status', { endpoint });
    if (!st.all && !st.club_ids.length) return;
    box.checked = st.announcements !== false;
    section.hidden = false;
  }).catch(() => { /* нет сети или push — секцию не показываем */ });
  box.addEventListener('change', async () => {
    box.disabled = true;
    try { await post('/api/push/preferences', { endpoint, announcements: box.checked }); toast(box.checked ? 'Объявления включены' : 'Объявления отключены'); }
    catch (e) { box.checked = !box.checked; toast(e.message || 'Не удалось сохранить', { kind: 'error' }); }
    finally { box.disabled = false; }
  });
  return section;
}

// Демо/офлайн-сборка (window.DemoBackend из android/shim/demo-backend.js): сброс случайных данных и быстрый вход в админку.
function demoSection() {
  const D = window.DemoBackend;
  if (!D) return null;
  const st = D.stats();
  const info = h('p', { class: 'field-hint', role: 'status' },
    `Данные хранятся только на этом устройстве. Кружков: ${st.clubs}, занятий: ${st.sessions}, изменений: ${st.exceptions}. Вход администратора выполнен автоматически.`);
  const reset = h('button', { type: 'button', class: 'btn btn--small', dataset: { demoReset: '' } }, 'Сбросить демо-данные');
  reset.addEventListener('click', () => {
    if (!confirm('Удалить все изменения и сгенерировать новые случайные данные?')) return;
    D.reset(); toast('Демо-данные пересозданы'); setTimeout(() => location.reload(), 400);
  });
  const admin = h('a', { class: 'btn btn--small btn--filled', href: '/admin/index.html' }, 'Открыть админку');
  return h('section', { class: 'sheet-section', dataset: { demoSection: '' } }, h('h3', {}, 'Демо-режим (офлайн)'), info,
    h('div', { class: 'form-actions' }, reset, admin));
}

function build() {
  const prefs = theme.get();
  const title = h('h2', { id: 'settings-title' }, 'Настройки');
  const close = h('button', { type: 'button', class: 'btn btn--text btn--small', 'aria-label': 'Закрыть настройки', onclick: () => dialog.close() }, icon('close'));
  const preview = h('p', { class: 'field-hint', id: 'settings-theme-hint' });
  const updateHint = () => {
    const t = theme.get();
    preview.textContent = t.theme === 'system' ? `Сейчас: ${theme.resolved() === 'dark' ? 'тёмная' : 'светлая'} (по настройке устройства)` : '';
  };
  const body = h('div', { class: 'sheet-body' },
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Тема'),
      radioGroup('theme', 'Тема оформления', THEMES, prefs.theme, v => { theme.set({ theme: v }); updateHint(); }), preview),
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Акцентный цвет'), swatches(prefs.accent, v => theme.set({ accent: v }))),
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Размер текста'),
      radioGroup('textSize', 'Размер текста', SIZES, prefs.textSize, v => theme.set({ textSize: v }))),
    announcementsSection(), serverSection(), demoSection());
  updateHint();
  const reset = h('button', { type: 'button', class: 'btn btn--text', onclick: () => { theme.set(theme.DEFAULTS); rebuild(); toast('Настройки сброшены'); } }, 'Сбросить');
  const done = h('button', { type: 'button', class: 'btn btn--filled', onclick: () => dialog.close() }, 'Готово');
  const foot = h('div', { class: 'sheet-foot' }, reset, done);
  dialog.replaceChildren(h('div', { class: 'sheet-head' }, title, close), body, foot);
}
function rebuild() { build(); }

function open(opener) {
  if (!dialog) {
    dialog = h('dialog', { class: 'sheet sheet--bottom', id: 'settings-dialog', 'aria-labelledby': 'settings-title' });
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }); // клик по подложке
    document.body.append(dialog);
  }
  build();
  dialog.showModal();
  dialog.querySelector('input:checked')?.focus();
  dialog.addEventListener('close', () => opener?.focus(), { once: true });
}

function mount() {
  if (!theme) return;
  installRipple();
  if (document.querySelector('[data-settings-button]')) return;
  const button = h('button', { type: 'button', class: 'settings-button', 'aria-label': 'Настройки', 'aria-haspopup': 'dialog', dataset: { settingsButton: '' } }, icon('gear'));
  button.addEventListener('click', () => open(button));
  const header = document.querySelector('[data-settings-slot]') || document.querySelector('.campus-header');
  if (header) header.append(button); else document.body.prepend(button);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
window.ClubsSettings = { open: () => open(document.querySelector('[data-settings-button]')) };
