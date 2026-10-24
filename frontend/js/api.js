// Публичные страницы всегда работают с настоящим backend: мок-режима и скрытых заглушек нет.
'use strict';

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function errorMessage(status, detail) {
  if (status >= 500) return 'Сервер временно недоступен. Попробуй ещё раз.';
  if (typeof detail === 'string') return detail;
  if (typeof detail?.message === 'string') return detail.message;
  if (Array.isArray(detail)) return detail.map(item => item.msg).filter(Boolean).join('; ') || 'Проверь введённые данные.';
  if (status === 401) return 'Нужно войти в систему.';
  if (status === 404) return 'Запрошенные данные не найдены.';
  return `Не удалось выполнить запрос (${status}).`;
}

// В Android-приложении (есть window.AppServer) cookie сессии между origin'ами не ходят — используем Bearer-токен из ответа /login.
// В обычном браузере токен НЕ хранится в JS: сессия живёт в HttpOnly-cookie.
const TOKEN_KEY = 'clubs.adminToken';
export const usesBearer = () => typeof window !== 'undefined' && !!window.AppServer;
const REFRESH_KEY = 'clubs.adminRefresh';
export function setAdminToken(token, refreshToken) {
  try {
    if (!usesBearer() || !token) return;
    localStorage.setItem(TOKEN_KEY, token);
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
  } catch { /* ignore */ }
}
export function clearAdminToken() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY); } catch { /* ignore */ } }
function adminToken() { try { return usesBearer() ? localStorage.getItem(TOKEN_KEY) : null; } catch { return null; } }

// Ротация refresh-токена: access живёт ~15 минут; на 401 один раз обновляем пару (single-flight) и повторяем запрос.
// В браузере refresh лежит в HttpOnly-cookie (JS его не видит), в приложении — в localStorage и уходит в теле.
let refreshing = null;
let generation = 0; // растёт после каждой успешной ротации: параллельные запросы с «старым» access просто повторяются
async function refreshSession() {
  if (!refreshing) {
    refreshing = (async () => {
      let body;
      if (usesBearer()) {
        const refresh_token = (() => { try { return localStorage.getItem(REFRESH_KEY); } catch { return null; } })();
        if (!refresh_token) return false;
        body = JSON.stringify({ refresh_token });
      }
      const response = await fetch('/api/admin/refresh', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body });
      if (response.status === 409) { generation += 1; return true; } // другая вкладка/запрос только что обновил токены — берём актуальные
      if (!response.ok) return false;
      const data = await response.json();
      setAdminToken(data.access_token, data.refresh_token);
      generation += 1;
      return true;
    })().catch(() => false).finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function request(path, options = {}) {
  const adminPath = path.startsWith('/api/admin') && path !== '/api/admin/login' && path !== '/api/admin/refresh';
  const usedGeneration = generation;
  try {
    return await send(path, options);
  } catch (error) {
    if (!adminPath || error?.status !== 401) throw error;
    const renewed = usedGeneration !== generation || (await refreshSession());
    if (renewed) {
      try { return await send(path, options); } catch (retryError) { if (retryError?.status !== 401) throw retryError; }
    }
    clearAdminToken();
    window.dispatchEvent?.(new CustomEvent('admin:unauthorized'));
    throw error;
  }
}

// Файл (например, .xlsx) с авторизацией админки: {blob, name}. 401 → одна попытка обновить сессию.
export async function requestBlob(path, { signal } = {}) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const headers = adminToken() ? { Authorization: `Bearer ${adminToken()}` } : {};
    let response;
    try { response = await fetch(path, { credentials: 'same-origin', headers, signal }); }
    catch (e) { if (e.name === 'AbortError') throw e; throw new ApiError('Не удалось связаться с сервером. Проверь подключение и повтори попытку.'); }
    if (response.status === 401 && attempt === 0 && (await refreshSession())) continue;
    if (!response.ok) {
      let detail; try { detail = (await response.json())?.detail; } catch { /* не JSON */ }
      throw new ApiError(errorMessage(response.status, detail), response.status, detail);
    }
    const cd = response.headers.get('Content-Disposition') || '';
    const name = decodeURIComponent((cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)/i) || [])[1] || 'download');
    return { blob: await response.blob(), name };
  }
  throw new ApiError(errorMessage(401));
}

async function send(path, options = {}) {
  const { signal, timeout = 15000, ...fetchOptions } = options;
  if (path.startsWith('/api/admin') && adminToken()) {
    fetchOptions.headers = { ...(fetchOptions.headers || {}), Authorization: `Bearer ${adminToken()}` };
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(path, { credentials: 'same-origin', ...fetchOptions, signal: controller.signal });
    if (/^\/api\/(schedule|clubs|categories|leaders|rooms)(\/|\?|$)/.test(path)) {
      window.dispatchEvent(new CustomEvent('public:cache-state', { detail: { path: path.split('?')[0],
        offline: response.headers.get('X-Clubs-Offline') === '1', savedAt: response.headers.get('X-Clubs-Cached-At') } }));
    }
    if (response.status === 204 || response.status === 205) return null;
    const raw = await response.text();
    let body;
    try { body = raw ? JSON.parse(raw) : null; }
    catch {
      if (response.ok) throw new ApiError('Сервер вернул данные в неожиданном формате.', response.status);
    }
    if (response.status === 429) {
      const wait = Number(response.headers.get('Retry-After'));
      throw new ApiError(wait > 0 ? `Слишком много попыток. Повтори через ${Math.ceil(wait / 60)} мин.` : 'Слишком много попыток. Повтори позже.', 429, body?.detail);
    }
    if (!response.ok) throw new ApiError(errorMessage(response.status, body?.detail), response.status, body?.detail);
    return body;
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Запрос отменён', 'AbortError');
    if (timedOut) throw new ApiError('Сервер долго не отвечает. Попробуй ещё раз.');
    if (error instanceof ApiError || error.name === 'AbortError') throw error;
    throw new ApiError('Не удалось связаться с сервером. Проверь подключение и повтори попытку.');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

function query(values) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (value !== '' && value !== null && value !== undefined) params.set(name, String(value));
  }
  return params.toString();
}

export const getCategories = options => request('/api/categories', options);
export const getLeaders = options => request('/api/leaders', options);
export const getRooms = options => request('/api/rooms', options);
export const getClubs = (filters = {}, options) => request(`/api/clubs?${query(filters)}`, options);

export async function getClub(id, options) {
  if (!Number.isInteger(id) || id <= 0) throw new ApiError('Кружок не найден.', 404);
  return request(`/api/clubs/${id}`, options);
}

export const getSchedule = (week, filters = {}, options) => request(`/api/schedule?${query({ week, ...filters })}`, options);
