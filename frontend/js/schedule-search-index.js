const indexes = new WeakMap();
let model;
export function prepareScheduleSearch(events, options) {
  if (!indexes.has(events)) {
    const promise = (model ||= import('./schedule-search-model.js'))
      .then(module => module.indexScheduleAsync(events, options)).catch(error => { indexes.delete(events); throw error; });
    indexes.set(events, promise);
  }
  return indexes.get(events);
}
