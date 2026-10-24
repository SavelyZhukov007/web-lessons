// Посещаемость: ротируемый QR занятия, живой список (опрос 2 с), ручная отметка и проверка по ID (только админ), статистика и Excel.
// Имён нет — только анонимные ID студентов (S-…).
import { h } from '../../ui.js';
import { request, requestBlob } from '../../api.js';
import { loadAll } from '../api.js';
import { pageHeader, loading, dataTable, formatDate, dayShort, confirmDialog, guarded } from '../kit.js';
import { moscowToday, dateKey } from '../../schedule-dates.js';

const send = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
let qrLib;
async function qrSvg(text) {
  if (!qrLib) {
    await new Promise((ok, fail) => { const s = document.createElement('script'); s.src = '/js/vendor/qrcode.js'; s.onload = ok; s.onerror = fail; document.head.append(s); });
    qrLib = window.qrcode;
  }
  const q = qrLib(0, 'M'); q.addData(text); q.make();
  const box = document.createElement('div'); box.className = 'attendance-qr-code';
  box.innerHTML = q.createSvgTag({ cellSize: 8, margin: 2, scalable: true });
  return box;
}

export async function mount(root, { signal }) {
  root.replaceChildren(loading());
  const data = await loadAll({ signal });
  const today = dateKey(moscowToday());
  const iso = d => { const [y, m, day] = d.split('-').map(Number); return new Date(y, m - 1, day).getDay() || 7; };
  const dateIn = h('input', { type: 'date', value: today, 'aria-label': 'Дата занятия' });
  const sessionSel = h('select', { 'aria-label': 'Занятие' });
  const qrBox = h('div', { class: 'attendance-qr', 'aria-live': 'polite' });
  const statsBox = h('div', {});
  const fromIn = h('input', { type: 'date', value: dateKey(new Date(moscowToday().getTime() - 30 * 864e5)), 'aria-label': 'С' });
  const toIn = h('input', { type: 'date', value: today, 'aria-label': 'По' });
  const clubSel = h('select', { 'aria-label': 'Кружок для выгрузки' }, h('option', { value: '' }, 'Все кружки (сводка + лист на кружок)'),
    ...[...data.club.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(c => h('option', { value: c.id }, c.name)));
  const xlsxBtn = h('button', { type: 'button', class: 'btn btn--tonal', 'data-attendance-xlsx': '' }, 'Скачать Excel (.xlsx)');
  xlsxBtn.addEventListener('click', async () => {
    xlsxBtn.disabled = true; const label = xlsxBtn.textContent; xlsxBtn.textContent = 'Готовлю файл…';
    try {
      const q = new URLSearchParams({ date_from: fromIn.value, date_to: toIn.value }); if (clubSel.value) q.set('club_id', clubSel.value);
      const { blob, name } = await requestBlob(`/api/admin/attendance/export.xlsx?${q}`);
      if (window.ItcFiles?.save) await window.ItcFiles.save(blob, name, 'Посещаемость'); // приложение: файл + «Поделиться»
      else { const a = h('a', { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
    } catch (e) { statsBox.prepend(h('div', { class: 'error-state', role: 'alert' }, e.message)); }
    finally { xlsxBtn.disabled = false; xlsxBtn.textContent = label; }
  });

  function fillSessions() {
    const wd = iso(dateIn.value || today);
    const list = data.sessions.filter(s => s.weekday === wd && data.club.get(s.club_id)?.is_active !== false)
      .sort((a, b) => a.start_time.localeCompare(b.start_time));
    sessionSel.replaceChildren(...(list.length ? list.map(s => h('option', { value: s.id }, `${s.start_time}–${s.end_time} · ${data.club.get(s.club_id)?.name ?? 'Кружок'}`))
      : [h('option', { value: '' }, `В ${dayShort(wd)} занятий нет`)]));
  }
  // QR занятия: открывается за 10 с до начала, выдаётся первые N минут, токен обновляется каждые ~25 с (действует 60 с).
  let timer = 0, poll = 0, live = null;
  const stopQr = () => { clearTimeout(timer); clearInterval(poll); timer = poll = 0; };
  signal?.addEventListener('abort', stopQr);
  const hm = t => new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const mmss = n => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  async function showQr() {
    stopQr();
    if (!sessionSel.value) return;
    const body = { session_id: Number(sessionSel.value), date: dateIn.value };
    qrBox.replaceChildren(loading());
    live = { sid: body.session_id, date: body.date, since: 0, list: h('ol', { class: 'attendance-live', 'aria-live': 'polite' }), count: h('strong', {}, '0') };
    const stage = h('div', { class: 'attendance-stage' });
    const manualIn = h('input', { placeholder: 'S-XXXX-XXXX-…', autocapitalize: 'characters', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'ID студента' });
    const manual = h('form', { class: 'attendance-form', onsubmit: async e => {
      e.preventDefault();
      if (await guarded(() => request('/api/admin/attendance/manual', send({ ...body, student_id: manualIn.value })), 'Отмечен вручную')) { manualIn.value = ''; pull(); }
    } }, h('label', {}, 'Отметить по ID', manualIn), h('button', { type: 'submit', class: 'btn btn--tonal' }, 'Отметить'));
    qrBox.replaceChildren(stage, h('h3', {}, 'Отметились: ', live.count), live.list, manual);
    async function tick() {
      let r;
      try { r = await request('/api/admin/attendance/qr', send(body)); } catch (e) { stage.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e.message)); return; }
      const title = h('p', { class: 'attendance-qr-title' }, `${r.club_name} · ${formatDate(r.date)}, ${r.start_time}–${r.end_time}`);
      if (r.state === 'early') {
        let left = r.opens_in; const c = h('span', {}, mmss(left));
        stage.replaceChildren(title, h('p', { class: 'attendance-state' }, 'QR ещё не готов — откроется через ', c));
        const step = () => { left -= 1; c.textContent = mmss(Math.max(0, left)); if (left <= 0) tick(); else timer = setTimeout(step, 1000); };
        timer = setTimeout(step, 1000); return;
      }
      if (r.state === 'closed') {
        stage.replaceChildren(title, h('p', { class: 'attendance-state' }, `Отметка закрыта (первые ${r.window_min} мин). Вручную по ID — до ${hm(r.manual_until)}.`)); return;
      }
      stage.replaceChildren(await qrSvg(r.token), title,
        h('p', { class: 'field-hint' }, `Студенты сканируют код в приложении «Кружки» → «Отметиться». Код меняется каждые ${r.rotate} с; приём отметок ещё ${Math.ceil(r.closes_in / 60)} мин.`));
      timer = setTimeout(tick, Math.min(r.rotate, Math.max(1, r.closes_in + 1)) * 1000);
    }
    tick();
    pull(); poll = setInterval(pull, 2000);
  }
  async function pull() {
    if (!live) return;
    const L = live;
    try {
      const r = await request(`/api/admin/attendance/live?session_id=${L.sid}&date=${L.date}&since_id=${L.since}`);
      L.count.textContent = String(r.count);
      for (const it of r.items) {
        L.since = Math.max(L.since, it.id);
        const li = h('li', { dataset: { id: it.id } }, h('code', { title: it.student_id }, it.short), h('time', {}, hm(it.at)), it.method === 'manual' ? h('span', { class: 'badge' }, 'вручную') : '',
          h('button', { type: 'button', class: 'btn btn--small btn--danger-text', onclick: async () => {
            if (await confirmDialog({ title: 'Удалить отметку?', message: `${it.student_id} — отметка будет удалена (запись в журнале аудита).` })
              && await guarded(() => request(`/api/admin/attendance/${it.id}`, { method: 'DELETE' }), 'Отметка удалена')) { li.remove(); L.count.textContent = String(Math.max(0, Number(L.count.textContent) - 1)); }
          } }, 'Удалить'));
        L.list.append(li);
      }
    } catch { /* следующий опрос */ }
  }
  async function loadStats() {
    statsBox.replaceChildren(loading());
    try {
      const s = await request(`/api/admin/attendance/stats?date_from=${fromIn.value}&date_to=${toIn.value}`, { signal });
      statsBox.replaceChildren(
        h('p', { class: 'attendance-total' }, `Всего отметок: ${s.total}`),
        dataTable({ caption: 'По кружкам', rows: s.clubs, empty: 'За период отметок нет',
          columns: [{ label: 'Кружок', key: 'club_name' }, { label: 'Занятий', cell: c => String(c.classes) },
            { label: 'Отметок', cell: c => String(c.checkins) }, { label: 'В среднем', cell: c => String(c.average) }] }),
        s.occurrences.length ? h('details', { class: 'attendance-details' }, h('summary', {}, 'По занятиям'),
          dataTable({ caption: 'По занятиям', rows: s.occurrences,
            columns: [{ label: 'Дата', cell: o => formatDate(o.date) }, { label: 'Время', key: 'start_time' }, { label: 'Кружок', key: 'club_name' }, { label: 'Отметок', cell: o => String(o.count) }] })) : '');
    } catch (e) { if (e.name !== 'AbortError') statsBox.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e.message)); }
  }
  const lookIn = h('input', { placeholder: 'S-XXXX-XXXX-…', autocapitalize: 'characters', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'ID студента' });
  const lookBox = h('div', { 'aria-live': 'polite' });
  const lookForm = h('form', { class: 'attendance-form', onsubmit: async e => {
    e.preventDefault(); lookBox.replaceChildren(loading());
    try {
      const r = await request(`/api/admin/attendance/student?student_id=${encodeURIComponent(lookIn.value)}`);
      lookBox.replaceChildren(h('p', {}, h('code', {}, r.student_id), ` — посещений за ${r.retention_days} дн.: ${r.items.length}`),
        dataTable({ caption: 'Посещения', rows: r.items, empty: 'Посещений нет',
          columns: [{ label: 'Дата', cell: o => formatDate(o.date) }, { label: 'Время', cell: o => `${o.start_time}–${o.end_time}` }, { label: 'Кружок', key: 'club_name' }, { label: 'Отметка', cell: o => `${hm(o.at)}${o.method === 'manual' ? ' (вручную)' : ''}` }] }));
    } catch (e2) { lookBox.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e2.message)); }
  } }, h('label', {}, 'ID студента', lookIn), h('button', { type: 'submit', class: 'btn btn--tonal' }, 'Проверить'));
  dateIn.addEventListener('change', () => { stopQr(); fillSessions(); });
  sessionSel.addEventListener('change', stopQr);
  fromIn.addEventListener('change', loadStats); toIn.addEventListener('change', loadStats);
  fillSessions();
  root.replaceChildren(
    pageHeader('Посещаемость'),
    h('section', { class: 'card attendance-card' }, h('h2', {}, 'QR-код занятия'),
      h('div', { class: 'attendance-form' }, h('label', {}, 'Дата', dateIn), h('label', {}, 'Занятие', sessionSel),
        h('button', { type: 'button', class: 'btn btn--filled', onclick: showQr }, 'Показать QR-код')), qrBox),
    h('section', { class: 'card attendance-card' }, h('h2', {}, 'Проверить посещение по ID'), h('p', { class: 'field-hint' }, 'Только для администратора. Данные о посещениях хранятся 21 день.'), lookForm, lookBox),
    h('section', { class: 'card attendance-card' }, h('h2', {}, 'Статистика'), h('div', { class: 'attendance-form' }, h('label', {}, 'С', fromIn), h('label', {}, 'По', toIn), h('label', {}, 'Выгрузка', clubSel), xlsxBtn), statsBox));
  loadStats();
}
