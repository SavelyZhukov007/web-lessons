// Клиент админ-API. Ошибки — ApiError из ../api.js (status, detail). 401 → событие admin:unauthorized (ловит index.js).
import { request, setAdminToken, clearAdminToken } from '../api.js';

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
export const exceptions = {
  ...crud('exceptions'),
  cancel: body => request('/api/admin/exceptions/cancellations', send('POST', { type: 'cancelled', ...body })),
  move: body => request('/api/admin/exceptions/moves', send('POST', { type: 'moved', ...body })),
};

/** Все справочники и расписание одним пакетом — нужны почти каждой вкладке (названия вместо id). */
export async function loadAll(options) {
  const [cats, lead, rms, cl, ss, ex] = await Promise.all([
    categories.list(options), leaders.list(options), rooms.list(options), clubs.list(options), sessions.list(options), exceptions.list(options)]);
  const by = list => new Map(list.map(item => [item.id, item]));
  return { categories: cats, leaders: lead, rooms: rms, clubs: cl, sessions: ss, exceptions: ex,
    cat: by(cats), leader: by(lead), room: by(rms), club: by(cl), session: by(ss) };
}
export const broadcasts = {
  list: options => request('/api/admin/broadcasts', options),
  estimate: (body, options) => request('/api/admin/broadcasts/estimate', { ...send('POST', body), ...options }),
  send: body => request('/api/admin/broadcasts', send('POST', body)),
};
