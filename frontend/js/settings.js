// Диалог «Настройки»: тема, акцент, размер текста, «Объявления» (если в браузере включены уведомления) (+ адрес сервера в Android-приложении).
// Подключается на каждой странице: <script type="module" src="/js/settings.js">. Кнопка-шестерёнка добавляется в шапку сама.
import { h, icon, toast, installRipple } from './ui.js';
import { request } from './api.js';

const theme = window.ClubsTheme;
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
  // 5-й образец — «радуга»: открывает выбор своего цвета (нативный <input type=color>)
  const picker = h('input', { type: 'color', class: 'swatch-picker', value: theme.get().customAccent, 'aria-label': 'Свой цвет акцента' });
  const label = h('label', { class: 'swatch swatch--custom', title: 'Свой цвет', dataset: { accent: 'custom' } }, picker,
    h('span', { 'aria-hidden': 'true' }, h('i', { class: 'swatch-dot' })));
  if (current === 'custom') label.classList.add('is-selected');
  const pickCustom = () => { theme.set({ accent: 'custom', customAccent: picker.value }); wrap.querySelectorAll('input[type=radio]').forEach(r => { r.checked = false; }); label.classList.add('is-selected'); };
  picker.addEventListener('input', pickCustom);
  picker.addEventListener('change', pickCustom);
  wrap.addEventListener('change', e => { if (e.target.type === 'radio') label.classList.remove('is-selected'); });
  wrap.append(label);
  return wrap;
}

const SUN = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.2M12 19.8V22M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2 12h2.2M19.8 12H22M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1z"/></svg>';

// Тумблер «Системная тема» + кнопка-иконка светлая ⇄ тёмная (видна, когда тумблер выключен)
function themeControl() {
  const sw = h('button', { type: 'button', class: 'switch', role: 'switch', id: 'settings-system-theme', 'aria-labelledby': 'settings-system-theme-label' }, h('span', { class: 'switch-thumb' }));
  const flip = h('button', { type: 'button', class: 'theme-flip' });
  const hint = h('p', { class: 'field-hint', id: 'settings-theme-hint' });
  const sync = () => {
    const pref = theme.get().theme, cur = theme.resolved();
    sw.setAttribute('aria-checked', String(pref === 'system'));
    flip.hidden = pref === 'system';
    flip.innerHTML = cur === 'dark' ? MOON : SUN;
    flip.dataset.mode = cur;
    flip.setAttribute('aria-label', cur === 'dark' ? 'Тёмная тема. Нажмите — светлая' : 'Светлая тема. Нажмите — тёмная');
    hint.textContent = pref === 'system' ? `Как на устройстве. Сейчас: ${cur === 'dark' ? 'тёмная' : 'светлая'}` : `Сейчас: ${cur === 'dark' ? 'тёмная' : 'светлая'} — нажмите на значок, чтобы сменить`;
  };
  sw.addEventListener('click', () => { theme.set({ theme: theme.themeFromToggle(theme.get().theme !== 'system', theme.resolved()) }); sync(); });
  flip.addEventListener('click', () => { theme.set({ theme: theme.nextManualTheme(theme.resolved()) }); sync(); });
  theme.onChange(sync);
  sync();
  return h('div', {}, h('div', { class: 'setting-row' }, h('span', { id: 'settings-system-theme-label', class: 'setting-row-label' }, 'Системная тема'), flip, sw), hint);
}

// Ползунок размера текста: три точки, живой предпросмотр при перетаскивании
function sizeSlider(current) {
  const names = Object.fromEntries(SIZES);
  const idx = Math.max(0, theme.SIZES.indexOf(current));
  const out = h('output', { class: 'size-current', for: 'settings-text-size' }, names[current] || 'Обычный');
  const range = h('input', { type: 'range', id: 'settings-text-size', class: 'size-range', min: 0, max: 2, step: 1, value: idx, 'aria-label': 'Размер текста' });
  const upd = () => { const v = theme.SIZES[+range.value]; range.setAttribute('aria-valuetext', names[v]); range.style.setProperty('--fill', `${range.value * 50}%`); out.textContent = names[v]; theme.set({ textSize: v }); };
  range.addEventListener('input', upd);
  range.setAttribute('aria-valuetext', names[current]); range.style.setProperty('--fill', `${idx * 50}%`);
  return h('div', { class: 'size-slider' }, h('div', { class: 'size-row' }, h('span', { class: 'size-a size-a--s', 'aria-hidden': 'true' }, 'А'), range, h('span', { class: 'size-a size-a--l', 'aria-hidden': 'true' }, 'А')),
    h('div', { class: 'size-ticks', 'aria-hidden': 'true' }, ...SIZES.map(([, t]) => h('span', {}, t))), out);
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

// «Админка» ⇄ «Расписание» (только для администратора) — вместо кнопок в верхней панели
function placeSection() {
  const inAdmin = /^\/admin\//.test(location.pathname);
  const link = h('a', { class: 'btn btn--tonal settings-place', href: inAdmin ? '/' : '/admin/login.html' }, inAdmin ? 'Расписание' : 'Вход для сотрудников');
  const section = h('section', { class: 'sheet-section', dataset: { placeSection: '' } }, link);
  if (!inAdmin) request('/api/admin/status').then(st => { if (st && st.admin) { link.href = '/admin/index.html'; link.textContent = 'Админка'; } }).catch(() => { /* не админ — ссылка на вход */ });
  return section;
}

// Аккаунт администратора: «Сменить пароль» и «Выйти» (в админке; window.ClubsAdmin ставит js/admin/index.js)
function accountSection() {
  const A = window.ClubsAdmin;
  if (!A) return null;
  const pw = h('button', { type: 'button', class: 'list-row' }, h('span', {}, 'Сменить пароль'), h('small', {}, A.login || ''));
  const out = h('button', { type: 'button', class: 'list-row list-row--danger' }, h('span', {}, 'Выйти'));
  pw.addEventListener('click', () => { dialog.close(); A.changePassword(); });
  out.addEventListener('click', () => { if (confirm('Выйти из аккаунта администратора?')) { dialog.close(); A.logout(); } });
  return h('section', { class: 'sheet-section' }, h('h3', {}, 'Аккаунт'), h('div', { class: 'list-group' }, pw, out));
}

function build() {
  const prefs = theme.get();
  const title = h('h2', { id: 'settings-title' }, 'Настройки');
  const close = h('button', { type: 'button', class: 'btn btn--text btn--small', 'aria-label': 'Закрыть настройки', onclick: () => dialog.close() }, icon('close'));
  const body = h('div', { class: 'sheet-body' },
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Тема'),
      themeControl()),
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Акцентный цвет'), swatches(prefs.accent, v => theme.set({ accent: v }))),
    h('section', { class: 'sheet-section' }, h('h3', {}, 'Размер текста'),
      sizeSlider(prefs.textSize)),
    announcementsSection(), accountSection(), placeSection(), serverSection(), demoSection());
  const reset = h('button', { type: 'button', class: 'btn btn--text', onclick: () => { theme.set(theme.DEFAULTS); rebuild(); toast('Настройки сброшены'); } }, 'Сбросить');
  const done = h('button', { type: 'button', class: 'btn btn--filled', onclick: () => dialog.close() }, 'Готово');
  const foot = h('div', { class: 'sheet-foot' }, reset, done);
  dialog.replaceChildren(h('div', { class: 'sheet-head sheet-head--center' }, h('span', { 'aria-hidden': 'true' }), title, close), body, foot);
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
