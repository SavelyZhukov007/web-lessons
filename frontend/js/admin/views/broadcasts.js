// «Рассылки»: объявление от админа всем или подписчикам выбранных кружков (при желании — только отдельных занятий).
// Доставка: Web Push сразу, приложение Android забирает объявления само (GET /api/announcements). Журнал — внизу.
import { h, toast } from '../../ui.js';
import { loadAll, broadcasts } from '../api.js';
import { pageHeader, loading, confirmDialog, dataTable, dayShort } from '../kit.js';
import { TITLE_MAX, BODY_MAX, buildPayload, filterClubs, audienceLabel, formatMsk, reachText, deliveryText, newIdempotencyKey } from '../broadcast-logic.js';

export async function mount(root, { signal }) {
  root.replaceChildren(pageHeader('Рассылки'), loading());
  const [data, history] = await Promise.all([loadAll({ signal }), broadcasts.list({ signal })]);
  const clubs = data.clubs.filter(c => c.is_active).sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  const sessionsOf = new Map();
  const sessionClub = new Map();
  for (const s of [...data.sessions].sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))) {
    if (!sessionsOf.has(s.club_id)) sessionsOf.set(s.club_id, []);
    sessionsOf.get(s.club_id).push(s);
    sessionClub.set(s.id, s.club_id);
  }

  const state = { title: '', body: '', url: '', audience: 'all', clubIds: new Set(), sessionIds: new Set(), key: newIdempotencyKey(), query: '' };
  const fresh = () => { state.key = newIdempotencyKey(); }; // правка текста = новое объявление

  // --- поля текста со счётчиками ---
  const counter = (max) => h('span', { class: 'bc-counter', 'aria-live': 'off' }, `0 / ${max}`);
  const titleCount = counter(TITLE_MAX);
  const bodyCount = counter(BODY_MAX);
  const titleInput = h('input', { id: 'bc-title', type: 'text', maxlength: TITLE_MAX, required: true, autocomplete: 'off', placeholder: 'Например: Собрание руководителей' });
  const bodyInput = h('textarea', { id: 'bc-body', maxlength: BODY_MAX, required: true, rows: 5, placeholder: 'Коротко и по делу: что, когда, где.' });
  const linkSelect = h('select', { id: 'bc-url' },
    h('option', { value: '' }, 'Без ссылки — откроется расписание'),
    h('option', { value: '/clubs.html' }, 'Каталог кружков'),
    clubs.map(c => h('option', { value: `/club.html?id=${c.id}` }, `Кружок: ${c.name}`)));
  const errorBox = h('p', { class: 'field-error', role: 'alert', hidden: true });

  // --- аудитория ---
  const audienceRadio = (value, text) => {
    const input = h('input', { type: 'radio', name: 'bc-audience', value, checked: state.audience === value });
    input.addEventListener('change', () => { state.audience = value; fresh(); renderAudience(); update(); });
    return h('label', {}, input, h('span', {}, text));
  };
  // Кружки: выбранные — чипы с ×; поиск с подсказками по мере ввода; отметка прямо в результатах
  const search = h('input', { type: 'search', id: 'bc-search', placeholder: 'Начните вводить название кружка', autocomplete: 'off', 'aria-controls': 'bc-club-list' });
  const chips = h('div', { class: 'bc-picked', 'aria-label': 'Выбранные кружки' });
  const list = h('div', { class: 'bc-club-list', id: 'bc-club-list', role: 'group', 'aria-label': 'Кружки' });
  const picked = h('p', { class: 'field-hint', role: 'status' });
  const toggleAll = h('button', { type: 'button', class: 'btn btn--text btn--small bc-expand', 'aria-expanded': 'false', 'aria-controls': 'bc-club-list' });
  let expanded = false;
  toggleAll.addEventListener('click', () => { expanded = !expanded; renderClubs(); });
  const clubsBox = h('div', { class: 'bc-clubs' },
    chips,
    h('label', { class: 'field', for: 'bc-search' }, h('span', { class: 'field-label' }, 'Найти кружок'), search), list, toggleAll, picked);
  search.addEventListener('input', () => { state.query = search.value; renderClubs(); });

  function setClub(id, on) {
    if (on) state.clubIds.add(id);
    else { state.clubIds.delete(id); for (const s of sessionsOf.get(id) ?? []) state.sessionIds.delete(s.id); }
    fresh(); renderClubs(); update();
  }
  function renderClubs() {
    const q = state.query.trim();
    const shown = filterClubs(clubs, q);
    const open = q || expanded;
    list.hidden = !open;
    toggleAll.hidden = !!q || !clubs.length;
    toggleAll.textContent = expanded ? 'Свернуть список' : `Показать все кружки (${clubs.length})`;
    toggleAll.setAttribute('aria-expanded', String(expanded));
    if (open) list.replaceChildren(...(shown.length ? shown.map(clubRow) : [h('p', { class: 'field-hint' }, clubs.length ? 'Ничего не нашлось.' : 'Активных кружков пока нет.')]));
    chips.replaceChildren(...[...state.clubIds].map(id => {
      const name = data.club.get(id)?.name ?? `#${id}`;
      const x = h('button', { type: 'button', class: 'bc-pill-x', 'aria-label': `Убрать «${name}»` }, '×');
      x.addEventListener('click', () => setClub(id, false));
      return h('span', { class: 'bc-pill' }, h('span', {}, name), x);
    }));
    chips.hidden = !state.clubIds.size;
    const n = state.clubIds.size;
    picked.textContent = n ? `Выбрано кружков: ${n}${state.sessionIds.size ? `, занятий: ${state.sessionIds.size}` : ''}. Без отмеченных занятий получат все подписчики кружка.` : 'Выберите один или несколько кружков.';
  }
  function clubRow(club) {
    const on = state.clubIds.has(club.id);
    const box = h('input', { type: 'checkbox', checked: on, id: `bc-club-${club.id}` });
    box.addEventListener('change', () => setClub(club.id, box.checked));
    const sessions = on ? sessionsOf.get(club.id) ?? [] : [];
    return h('div', { class: 'bc-club', dataset: on ? { on: '' } : {} },
      h('label', { class: 'bc-check', for: `bc-club-${club.id}` }, box, h('span', {}, club.name)),
      sessions.length > 0 && h('div', { class: 'bc-sessions', role: 'group', 'aria-label': `Занятия кружка ${club.name} (необязательно)` },
        sessions.map(s => {
          const chip = h('input', { type: 'checkbox', checked: state.sessionIds.has(s.id) });
          chip.addEventListener('change', () => { if (chip.checked) state.sessionIds.add(s.id); else state.sessionIds.delete(s.id); fresh(); renderClubs(); update(); });
          return h('label', { class: 'bc-chip' }, chip, `${dayShort(s.weekday)} ${s.start_time}`);
        })));
  }
  const audienceSlot = h('div', {});
  function renderAudience() {
    audienceSlot.replaceChildren(...(state.audience === 'clubs' ? [clubsBox] : [h('p', { class: 'field-hint' }, 'Получат все, кто включил уведомления.')]));
    if (state.audience === 'clubs') renderClubs();
  }

  // --- охват и предпросмотр ---
  const reach = h('p', { class: 'bc-reach', role: 'status', 'aria-live': 'polite' }, 'Считаю получателей…');
  const pvTitle = h('strong', {});
  const pvBody = h('p', {});
  const preview = h('div', { class: 'bc-preview', 'aria-label': 'Так будет выглядеть уведомление' },
    h('img', { src: '/icons/icon-192.png', alt: '' }), h('small', {}, 'KipClub · сейчас'), pvTitle, pvBody);
  const send = h('button', { type: 'submit', class: 'btn btn--filled', form: 'bc-form' }, 'Отправить…');

  let reachTimer, reachCtrl, lastReach = { web: 0, apk: 0 };
  function scheduleReach() {
    clearTimeout(reachTimer);
    reachTimer = setTimeout(async () => {
      reachCtrl?.abort();
      reachCtrl = new AbortController();
      const { payload } = buildPayload({ ...state, sessionClub, title: 'x', body: 'x' });
      if (payload.audience === 'clubs' && !payload.club_ids.length) { lastReach = { web: 0, apk: 0 }; reach.textContent = 'Выберите кружки, чтобы увидеть охват.'; return; }
      try {
        lastReach = await broadcasts.estimate({ audience: payload.audience, club_ids: payload.club_ids ?? [], session_ids: payload.session_ids ?? [] }, { signal: reachCtrl.signal });
        reach.textContent = reachText(lastReach);
      } catch (e) { if (e.name !== 'AbortError') reach.textContent = 'Не удалось посчитать получателей.'; }
    }, 250);
  }
  function update() {
    state.title = titleInput.value; state.body = bodyInput.value; state.url = linkSelect.value;
    titleCount.textContent = `${state.title.length} / ${TITLE_MAX}`;
    bodyCount.textContent = `${state.body.length} / ${BODY_MAX}`;
    pvTitle.textContent = state.title.trim() || 'Заголовок';
    pvBody.textContent = state.body.trim() || 'Текст объявления';
    pvTitle.toggleAttribute('data-empty', !state.title.trim());
    pvBody.toggleAttribute('data-empty', !state.body.trim());
    scheduleReach();
  }
  for (const el of [titleInput, bodyInput]) el.addEventListener('input', () => { fresh(); errorBox.hidden = true; update(); });
  linkSelect.addEventListener('change', () => { fresh(); update(); });

  const form = h('form', { class: 'form-grid bc-form', id: 'bc-form', novalidate: true },
    h('label', { class: 'field', for: 'bc-title' }, h('span', { class: 'field-label' }, 'Заголовок *'), titleInput), titleCount,
    h('label', { class: 'field', for: 'bc-body' }, h('span', { class: 'field-label' }, 'Текст *'), bodyInput), bodyCount,
    h('label', { class: 'field', for: 'bc-url' }, h('span', { class: 'field-label' }, 'По нажатию открыть'), linkSelect),
    h('fieldset', { class: 'field' }, h('legend', { class: 'field-label' }, 'Кому'),
      h('div', { class: 'segmented bc-audience', role: 'radiogroup', 'aria-label': 'Кому отправить' }, audienceRadio('all', 'Всем'), audienceRadio('clubs', 'Кружкам')), audienceSlot),
    errorBox,
    h('div', { class: 'form-actions' }, send));

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const { errors, payload } = buildPayload({ ...state, sessionClub });
    const first = Object.values(errors)[0];
    if (first) {
      errorBox.textContent = first; errorBox.hidden = false;
      (errors.title ? titleInput : errors.body ? bodyInput : search).focus();
      return;
    }
    const who = payload.audience === 'all' ? 'всем подписчикам' : `подписчикам: ${audienceLabel({ audience: 'clubs', club_names: payload.club_ids.map(id => data.club.get(id)?.name ?? `#${id}`) })}${payload.session_ids.length ? ` (занятий: ${payload.session_ids.length})` : ''}`;
    const ok = await confirmDialog({ title: 'Отправить объявление?', message: `«${payload.title}» уйдёт ${who}. ${reachText(lastReach)}. Отменить отправку будет нельзя.`, confirmLabel: 'Отправить', danger: false });
    if (!ok) return;
    send.disabled = true; send.textContent = 'Отправляю…';
    try {
      const result = await broadcasts.send(payload);
      toast(result.duplicate ? 'Это объявление уже отправлено' : `Отправлено. ${deliveryText(result)}`);
      titleInput.value = ''; bodyInput.value = ''; linkSelect.value = '';
      state.audience = 'all'; state.clubIds.clear(); state.sessionIds.clear(); state.query = ''; search.value = ''; expanded = false;
      form.querySelector('input[value="all"]').checked = true;
      fresh(); renderAudience(); update();
      renderHistory(await broadcasts.list());
    } catch (error) {
      errorBox.textContent = error?.message || 'Не удалось отправить.'; errorBox.hidden = false;
    } finally { send.disabled = false; send.textContent = 'Отправить…'; }
  });

  // --- журнал ---
  const historySlot = h('section', { class: 'bc-history', 'aria-labelledby': 'bc-history-title' });
  function renderHistory(items) {
    historySlot.replaceChildren(h('h2', { id: 'bc-history-title' }, 'Отправленные'),
      dataTable({
        caption: 'Отправленные объявления, сначала новые',
        empty: 'Объявлений ещё не было.',
        rows: items,
        columns: [
          { label: 'Когда', cell: r => h('time', { datetime: r.created_at }, formatMsk(r.created_at)) },
          { label: 'Автор', cell: r => r.author || '—' },
          { label: 'Кому', cell: r => audienceLabel(r) + (r.session_ids?.length ? ` · занятий: ${r.session_ids.length}` : '') },
          { label: 'Объявление', cell: r => h('div', {}, h('strong', {}, r.title), h('div', { class: 'field-hint' }, r.body)) },
          { label: 'Доставка', cell: r => deliveryText(r) },
        ],
      }));
  }

  root.replaceChildren(
    pageHeader('Рассылки'),
    h('div', { class: 'bc-layout' },
      h('section', { class: 'card', 'aria-labelledby': 'bc-new' }, h('h2', { id: 'bc-new' }, 'Новое объявление'), form),
      h('aside', { class: 'card bc-side', 'aria-labelledby': 'bc-pv' }, h('h2', { id: 'bc-pv' }, 'Предпросмотр'), preview, h('h3', {}, 'Охват'), reach)),
    historySlot);
  renderAudience();
  renderHistory(history);
  update();
  signal?.addEventListener('abort', () => { clearTimeout(reachTimer); reachCtrl?.abort(); });
  root.querySelector('#view-title').focus({ preventScroll: true });
}
