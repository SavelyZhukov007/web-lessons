// В итоговой версии все публичные страницы работают с настоящим backend.
// true — только для локальной разработки; скрытого перехода на заглушки нет.
export const USE_MOCKS = false;

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

export async function request(path, options = {}) {
  const { signal, timeout = 15000, ...fetchOptions } = options;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(path, { credentials: 'same-origin', ...fetchOptions, signal: controller.signal });
    if (response.status === 204 || response.status === 205) return null;
    const raw = await response.text();
    let body;
    try { body = raw ? JSON.parse(raw) : null; }
    catch {
      if (response.ok) throw new ApiError('Сервер вернул данные в неожиданном формате.', response.status);
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

async function mockData(options) { return request('/mock-data.json', options); }

export async function getCategories(options) {
  return USE_MOCKS ? (await mockData(options)).categories : request('/api/categories', options);
}

export async function getLeaders(options) {
  return USE_MOCKS ? (await mockData(options)).leaders : request('/api/leaders', options);
}

export async function getRooms(options) {
  return USE_MOCKS ? (await mockData(options)).rooms : request('/api/rooms', options);
}

export async function getClubs(filters = {}, options) {
  if (!USE_MOCKS) return request(`/api/clubs?${query(filters)}`, options);
  return (await mockData(options)).clubs.filter(club => club.is_active
    && (!filters.category_id || club.category_id === Number(filters.category_id))
    && (!filters.search || `${club.name} ${club.description}`.toLocaleLowerCase('ru').includes(filters.search.toLocaleLowerCase('ru'))));
}

export async function getClub(id, options) {
  if (!Number.isInteger(id) || id <= 0) throw new ApiError('Кружок не найден.', 404);
  if (!USE_MOCKS) return request(`/api/clubs/${id}`, options);
  const club = (await getClubs({}, options)).find(item => item.id === id);
  if (!club) throw new ApiError('Кружок не найден.', 404);
  return club;
}

export async function getSchedule(week, filters = {}, options) {
  if (!USE_MOCKS) return request(`/api/schedule?${query({ week, ...filters })}`, options);
  const { parseDate, addDays, dateKey } = await import('./schedule-dates.js');
  const start = parseDate(week);
  if (!start) throw new ApiError('Некорректная дата недели.', 422);
  const end = dateKey(addDays(start, 6));
  // В макете отбираем готовые события; генерацией повторений занимается backend.
  return (await mockData(options)).schedule_events.filter(event => event.date >= week && event.date <= end
    && ['category_id', 'leader_id', 'room_id'].every(key => !filters[key] || event[key] === Number(filters[key]))
    && (!filters.weekday || parseDate(event.date)?.getDay() === Number(filters.weekday))
    && (!filters.search || event.club_name.toLocaleLowerCase('ru').includes(filters.search.toLocaleLowerCase('ru'))));
}
