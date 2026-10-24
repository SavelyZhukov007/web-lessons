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

  let choices = new Map(), choiceSeq = 0;
  async function fillSessions() {
    const mine = ++choiceSeq;
    sessionSel.disabled = true;
    sessionSel.replaceChildren(h('option', { value: '' }, 'Загрузка занятий…'));
    try {
      const list = await request(`/api/admin/attendance/occurrences?date=${encodeURIComponent(dateIn.value || today)}`, { signal });
      if (mine !== choiceSeq || signal?.aborted) return;
      choices = new Map(list.map(s => [s.event_id, s]));
      sessionSel.replaceChildren(...(list.length ? list.map(s => h('option', { value: s.event_id },
        `${s.start_time}–${s.end_time} · ${s.club_name}${s.status === 'moved' ? ' · перенос' : ''}`))
        : [h('option', { value: '' }, 'В эту дату занятий нет')]));
    } catch (e) {
      if (mine !== choiceSeq || signal?.aborted) return;
      choices.clear();
      sessionSel.replaceChildren(h('option', { value: '' }, 'Не удалось загрузить занятия'));
      qrBox.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e.message,
        h('button', { type: 'button', class: 'btn', onclick: fillSessions }, 'Повторить')));
    } finally { if (mine === choiceSeq) sessionSel.disabled = false; }
  }
  // QR занятия: открывается за 10 с до начала, выдаётся первые N минут, токен обновляется каждые ~25 с (действует 60 с).
  let timer = 0, poll = 0, live = null, generation = 0;
  const stopQr = () => { ++generation; clearTimeout(timer); clearInterval(poll); timer = poll = 0; live = null; qrBox.replaceChildren(); };
  signal?.addEventListener('abort', stopQr);
  const hm = t => new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const mmss = n => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  async function showQr() {
    stopQr();
    const event = choices.get(sessionSel.value);
    if (!event || signal?.aborted) return;
    const mine = generation;
    const active = () => mine === generation && !signal?.aborted;
    const body = { session_id: event.session_id, date: dateIn.value, original_date: event.original_date };
    qrBox.replaceChildren(loading());
    live = { sid: body.session_id, date: body.date, original: body.original_date, since: 0, busy: false,
      status: h('p', { class: 'field-hint', role: 'status' }), list: h('ol', { class: 'attendance-live', 'aria-live': 'polite' }), count: h('strong', {}, '0') };
    const stage = h('div', { class: 'attendance-stage' });
    const manualIn = h('input', { placeholder: 'S-XXXX-XXXX-…', autocapitalize: 'characters', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'ID студента' });
    const manual = h('form', { class: 'attendance-form', onsubmit: async e => {
      e.preventDefault();
      if (await guarded(() => request('/api/admin/attendance/manual', send({ ...body, student_id: manualIn.value })), 'Отмечен вручную')) { manualIn.value = ''; pull(); }
    } }, h('label', {}, 'Отметить по ID', manualIn), h('button', { type: 'submit', class: 'btn btn--tonal' }, 'Отметить'));
    qrBox.replaceChildren(stage, h('h3', {}, 'Отметились: ', live.count), live.status, live.list, manual);
    async function tick() {
      if (!active()) return;
      let r;
      try { r = await request('/api/admin/attendance/qr', { ...send(body), signal }); } catch (e) {
        if (active()) stage.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e.message)); return;
      }
      if (!active()) return;
      const title = h('p', { class: 'attendance-qr-title' }, `${r.club_name} · ${formatDate(r.date)}, ${r.start_time}–${r.end_time}`);
      if (r.state === 'early') {
        let left = r.opens_in; const c = h('span', {}, mmss(left));
        stage.replaceChildren(title, h('p', { class: 'attendance-state' }, 'QR ещё не готов — откроется через ', c));
        const step = () => { if (!active()) return; left -= 1; c.textContent = mmss(Math.max(0, left)); if (left <= 0) tick(); else timer = setTimeout(step, 1000); };
        timer = setTimeout(step, 1000); return;
      }
      if (r.state === 'closed') {
        stage.replaceChildren(title, h('p', { class: 'attendance-state' }, `Отметка закрыта (первые ${r.window_min} мин). Вручную по ID — до ${hm(r.manual_until)}.`)); return;
      }
      const svg = await qrSvg(r.token);
      if (!active()) return;
      stage.replaceChildren(svg, title,
        h('p', { class: 'field-hint' }, `Студенты сканируют код в приложении «Кружки» → «Отметиться». Код меняется каждые ${r.rotate} с; приём отметок ещё ${Math.ceil(r.closes_in / 60)} мин.`));
      timer = setTimeout(tick, Math.min(r.rotate, Math.max(1, r.closes_in + 1)) * 1000);
    }
    tick();
    pull(); poll = setInterval(pull, 2000);
  }
  async function pull() {
    if (!live || live.busy || signal?.aborted) return;
    const L = live;
    L.busy = true;
    try {
      const r = await request(`/api/admin/attendance/live?session_id=${L.sid}&date=${L.date}&original_date=${L.original}`, { signal });
      if (L !== live || signal?.aborted) return;
      const currentIds = new Set(r.items.map(it => String(it.id)));
      for (const row of L.list.children) if (!currentIds.has(row.dataset.id)) row.remove();
      L.status.textContent = `Обновлено в ${new Date().toLocaleTimeString('ru-RU')}`;
      L.count.textContent = String(r.count);
      for (const it of r.items) {
        if ([...L.list.children].some(row => row.dataset.id === String(it.id))) continue;
        L.since = Math.max(L.since, it.id);
        const li = h('li', { dataset: { id: it.id } }, h('code', { title: it.student_id }, it.short), h('time', {}, hm(it.at)), it.method === 'manual' ? h('span', { class: 'badge' }, 'вручную') : '',
          h('button', { type: 'button', class: 'btn btn--small btn--danger-text', onclick: async () => {
            if (await confirmDialog({ title: 'Удалить отметку?', message: `${it.student_id} — отметка будет удалена (запись в журнале аудита).` })
              && await guarded(() => request(`/api/admin/attendance/${it.id}`, { method: 'DELETE' }), 'Отметка удалена')) { li.remove(); L.count.textContent = String(Math.max(0, Number(L.count.textContent) - 1)); }
          } }, 'Удалить'));
        L.list.append(li);
      }
    } catch { if (L === live) L.status.textContent = 'Нет обновлений: проверьте соединение. Повторная попытка через 2 секунды.'; }
    finally { L.busy = false; }
  }
  let statsSeq = 0;
  async function loadStats() {
    const mine = ++statsSeq;
    statsBox.replaceChildren(loading());
    try {
      const s = await request(`/api/admin/attendance/stats?date_from=${fromIn.value}&date_to=${toIn.value}`, { signal });
      if (mine !== statsSeq || signal?.aborted) return;
      statsBox.replaceChildren(
        h('p', { class: 'attendance-total' }, `Всего отметок: ${s.total}`),
        dataTable({ caption: 'По кружкам', rows: s.clubs, empty: 'За период отметок нет',
          columns: [{ label: 'Кружок', key: 'club_name' }, { label: 'Занятий с отметками', cell: c => String(c.classes) },
            { label: 'Отметок', cell: c => String(c.checkins) }, { label: 'В среднем', cell: c => String(c.average) }] }),
        s.occurrences.length ? h('details', { class: 'attendance-details' }, h('summary', {}, 'По занятиям'),
          dataTable({ caption: 'По занятиям', rows: s.occurrences,
            columns: [{ label: 'Дата', cell: o => formatDate(o.date) }, { label: 'Время', key: 'start_time' }, { label: 'Кружок', key: 'club_name' }, { label: 'Отметок', cell: o => String(o.count) }] })) : '');
    } catch (e) { if (mine === statsSeq && e.name !== 'AbortError') statsBox.replaceChildren(h('div', { class: 'error-state', role: 'alert' }, e.message)); }
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
