// Алиса: страницы используют только эти функции. Переключение на API — здесь.
// Моки включены явно; при API-ошибке НЕ переключайтесь на них молча.
export const USE_MOCKS = true;
async function mockData() {
  const response = await fetch('/mock-data.json');
  if (!response.ok) throw new Error('Не удалось загрузить тестовые данные');
  return response.json();
}
export async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Ошибка API (${response.status})`);
  return response.json();
}
export async function getClubs() {
  return USE_MOCKS ? (await mockData()).clubs.filter(club => club.is_active) : request('/api/clubs');
}
export async function getClub(id) {
  return USE_MOCKS ? (await getClubs()).find(club => club.id === id) : request(`/api/clubs/${id}`);
}
export async function getSchedule(week) {
  // Только готовые события. Раскрытие регулярных занятий делает backend.
  return USE_MOCKS ? (await mockData()).schedule_events : request(`/api/schedule?week=${encodeURIComponent(week)}`);
}
