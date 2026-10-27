// Клиент админ-API. Ошибки — ApiError из ../api.js (status, detail). 401 → событие admin:unauthorized (ловит index.js).
import { request as baseRequest, setAdminToken, clearAdminToken } from '../api.js';

// A 409 without a confirmation token remains a blocking validation error.
// Each retry rechecks the schedule; a changed conflict set needs a new decision.
async function request(path, options = {}) {
  const confirmed = [];
  for (;;) {
    try {
      return await baseRequest(path, confirmed.length
        ? { ...options, headers: { ...(options.headers || {}), 'X-Confirmed-Conflicts': confirmed.join(',') } }
        : options);
    } catch (error) {
      const detail = error?.detail;
      const token = detail?.confirmation_token;
      if (error?.status !== 409 || !token || !Array.isArray(detail.conflicts) || confirmed.includes(token) || confirmed.length >= 30) throw error;
      const reasons = { room: 'общая аудитория', leader: 'общий руководитель', group: 'общая группа' };
      const lines = detail.conflicts.map(c => {
        const date = c.date ? c.date.split('-').reverse().join('.') : '';
        const reason = (c.reasons || []).map(r => reasons[r] || r).join(', ');
        const more = c.dates_total > 1 ? ` (дат пересечения: ${c.dates_total})` : '';
        return `• ${c.club_name || 'Занятие'}: ${date} ${c.start_time || ''}–${c.end_time || ''}; ${reason}${more}`;
      });
      if (!window.confirm(`${detail.message || 'Есть пересечения в расписании.'}\n\n${lines.join('\n')}\n\nСохранить несмотря на пересечения?\n«Отмена» — вернуться и исправить.`)) throw error;
      confirmed.push(token);
    }
  }
}

const send = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export async function login(loginName, password) {
  const result = await request('/api/admin/login', send('POST', { login: loginName, password }));
  setAdminToken(result.access_token, result.refresh_token); // только в приложении (Bearer); в браузере сессия — HttpOnly-cookie
  return result;
}
export async function logout() {
  try { await request('/api/admin/logout', { method: 'POST' }); } finally { clearAdminToken(); }
}
export const getAdminStatus = options => request('/api/admin/status', options);
export const getStats = options => request('/api/admin/stats', options);
export const changePassword = (current_password, new_password) => request('/api/admin/password', send('POST', { current_password, new_password }));

function crud(path) {
  return {
    list: options => request(`/api/admin/${path}`, options),
    create: body => request(`/api/admin/${path}`, send('POST', body)),
    update: (id, body) => request(`/api/admin/${path}/${id}`, send('PATCH', body)),
    remove: id => request(`/api/admin/${path}/${id}`, { method: 'DELETE' }),
  };
}
export const categories = crud('categories');
export const leaders = crud('leaders');
export const rooms = crud('rooms');
export const clubs = crud('clubs');
export const sessions = crud('sessions');
export const periods = { ...crud('periods'), update: (id, body) => request(`/api/admin/periods/${id}`, send('PUT', body)),
  days: id => request(`/api/admin/periods/${id}/days-off`),
  addDay: (id, body) => request(`/api/admin/periods/${id}/days-off`, send('POST', body)),
  addDays: (id, body) => request(`/api/admin/periods/${id}/days-off/range`, send('POST', body)),
  removeDay: (id, day) => request(`/api/admin/periods/${id}/days-off/${day}`, { method: 'DELETE' }) };
export const imports = {
  list: options => request('/api/admin/imports', options),
  create: body => request('/api/admin/imports', send('POST', body)),
  decisions: (id, decisions) => request(`/api/admin/imports/${id}/decisions`, send('PUT', { decisions })),
  publish: id => request(`/api/admin/imports/${id}/publish`, { method: 'POST' }),
};
export const exceptions = {
  ...crud('exceptions'),
  cancel: body => request('/api/admin/exceptions/cancellations', send('POST', { type: 'cancelled', ...body })),
  move: body => request('/api/admin/exceptions/moves', send('POST', { type: 'moved', ...body })),
};

/** Все справочники и расписание одним пакетом — нужны почти каждой вкладке (названия вместо id). */
export async function loadAll(options) {
  const [cats, lead, rms, cl, ss, ex] = await Promise.all([
    categories.list(options), leaders.list(options), rooms.list(options), clubs.list(options), sessions.list(options), exceptions.list(options)]);
  if (options?.signal?.aborted) throw new DOMException('Запрос отменён', 'AbortError');
  const by = list => new Map(list.map(item => [item.id, item]));
  return { categories: cats, leaders: lead, rooms: rms, clubs: cl, sessions: ss, exceptions: ex,
    cat: by(cats), leader: by(lead), room: by(rms), club: by(cl), session: by(ss) };
}
export const broadcasts = {
  list: async options => {
    const result = await request('/api/admin/broadcasts', { cache: 'no-store', ...options });
    return Array.isArray(result) ? result : result.items;
  },
  estimate: (body, options) => request('/api/admin/broadcasts/estimate', { ...send('POST', body), ...options }),
  send: body => request('/api/admin/broadcasts', send('POST', body)),
};
