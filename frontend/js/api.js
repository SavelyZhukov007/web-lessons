export const USE_MOCKS = true;

async function mockData() {
  const response = await fetch('/mock-data.json');
  if (!response.ok) throw new Error('Не удалось загрузить тестовые данные');
  return response.json();
}

export async function request(path, options = {}) {
  const response = await fetch(path, options);
  
  // 204 - No Content
  // for logout
  const data = response.status === 204
    ? null
    : await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      data?.detail ?? `Ошибка API (${response.status})`
    );
  }
  return data;
}

export async function getClubs() {
  return USE_MOCKS ? (await mockData()).clubs.filter(club => club.is_active) : request('/api/clubs');
}

export async function getClub(id) {
  return USE_MOCKS ? (await getClubs()).find(club => club.id === id) : request(`/api/clubs/${id}`);
}

export async function getSchedule(week) {
  return USE_MOCKS ? (await mockData()).schedule_events : request(`/api/schedule?week=${encodeURIComponent(week)}`);
}
