// Сведения о неделе запрашиваются у сервера, который определяет чётность.
export function createPeriodDisplay(anchor, currentWeek) {
  const box = document.createElement('p');
  box.className = 'field-hint';
  box.setAttribute('role', 'status');
  anchor.after(box);
  let request = 0;
  return async week => {
    const id = ++request;
    box.textContent = '';
    try {
      const response = await fetch(`/api/periods/week?week=${encodeURIComponent(week)}`);
      if (!response.ok) return;
      const periods = await response.json();
      if (id !== request || currentWeek() !== week || !Array.isArray(periods)) return;
      box.textContent = periods.map(p => p.status === 'ended' ? `${p.name}: период завершён` : p.status === 'upcoming' ? `${p.name}: начинается ${p.start_date.split('-').reverse().join('.')}` : `${p.name}: ${p.parity === 'even' ? 'чётная' : 'нечётная'} неделя${p.no_class_days?.length ? ` · без занятий: ${p.no_class_days.map(d => d.date.split('-').reverse().join('.')).join(', ')}` : ''}`).join('; ');
    } catch { /* отсутствие сети не меняет расписание */ }
  };
}
