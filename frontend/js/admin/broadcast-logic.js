// Чистая логика экрана «Рассылки» (без DOM): проверка формы, тело запроса, подписи аудитории, время МСК, поиск кружков.
export const TITLE_MAX = 80;
export const BODY_MAX = 500;

const fold = s => String(s ?? '').toLowerCase().replace(/ё/g, 'е').trim();

/** Кружки, подходящие под поиск (по названию, без учёта регистра и «ё»). */
export function filterClubs(clubs, query) {
  const q = fold(query);
  return q ? clubs.filter(c => fold(c.name).includes(q)) : clubs.slice();
}

/** Случайный ключ идемпотентности: один набранный текст — одна рассылка, даже при двойном нажатии/ретрае. */
export function newIdempotencyKey(rand = globalThis.crypto) {
  const bytes = new Uint8Array(16);
  rand.getRandomValues(bytes);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

/** state: {title, body, url, audience:'all'|'clubs', clubIds:Set|[], sessionIds:Set|[], key}. → {errors, payload}. */
export function buildPayload(state) {
  const title = String(state.title ?? '').trim();
  const body = String(state.body ?? '').trim();
  const clubIds = [...(state.clubIds ?? [])].map(Number).sort((a, b) => a - b);
  const errors = {};
  if (!title) errors.title = 'Введите заголовок';
  else if (title.length > TITLE_MAX) errors.title = `Не длиннее ${TITLE_MAX} символов`;
  if (!body) errors.body = 'Введите текст объявления';
  else if (body.length > BODY_MAX) errors.body = `Не длиннее ${BODY_MAX} символов`;
  const audience = state.audience === 'clubs' ? 'clubs' : 'all';
  if (audience === 'clubs' && !clubIds.length) errors.audience = 'Выберите хотя бы один кружок или «Всем»';
  const payload = { title, body, audience, idempotency_key: state.key };
  if (state.url) payload.url = state.url;
  if (audience === 'clubs') {
    payload.club_ids = clubIds;
    const own = new Set(clubIds);
    payload.session_ids = [...(state.sessionIds ?? [])].map(Number).filter(id => own.has(Number(state.sessionClub?.get?.(id) ?? NaN)) || !state.sessionClub)
      .sort((a, b) => a - b);
  }
  return { errors, payload };
}

/** Подпись аудитории для журнала и подтверждения. */
export function audienceLabel(item) {
  if (item.audience !== 'clubs') return 'Всем';
  const names = item.club_names ?? [];
  if (!names.length) return 'Подписчикам кружков';
  return names.length <= 3 ? names.join(', ') : `${names.slice(0, 3).join(', ')} и ещё ${names.length - 3}`;
}

/** «25.10.2026, 20:15 МСК» из ISO-времени UTC (с Z). */
export function formatMsk(iso) {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '';
  const d = new Date(t + 3 * 3600e3);
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getUTCDate())}.${p(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}, ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} МСК`;
}

const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};

/** Оценка охвата по каналам: {web, apk} → строка. */
export function reachText({ web = 0, apk = 0 } = {}) {
  return `Браузеры (Web Push): ${web} ${plural(web, 'подписка', 'подписки', 'подписок')} · Приложение Android: ${apk} ${plural(apk, 'устройство', 'устройства', 'устройств')}`;
}

/** Итог доставки одной рассылки для журнала. */
export function deliveryText(item) {
  const web = item.web_failed ? `${item.web_sent} отправлено, ${item.web_failed} с ошибкой` : `${item.web_sent} отправлено`;
  return `Web Push: ${web} · Android: ${item.apk_targets} ${plural(item.apk_targets, 'устройство', 'устройства', 'устройств')}`;
}
