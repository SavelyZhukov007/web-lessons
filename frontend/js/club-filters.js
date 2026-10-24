// Читаем и нормализуем только фильтры каталога кружков.
export function readClubFilters(query) {
  const params = new URLSearchParams(query);
  const rawCategory = params.get('category_id') || '';
  return {
    search: (params.get('search') || '').trim().slice(0, 200),
    category_id: /^[1-9]\d*$/.test(rawCategory) ? rawCategory : '',
  };
}

// Возвращаем адрес той же страницы, сохраняя остальные параметры и якорь.
export function buildClubUrl(href, values) {
  const url = new URL(href);
  const filters = readClubFilters(new URLSearchParams(values));
  for (const [name, value] of Object.entries(filters)) {
    if (value) url.searchParams.set(name, value);
    else url.searchParams.delete(name);
  }
  return url.pathname + url.search + url.hash;
}
