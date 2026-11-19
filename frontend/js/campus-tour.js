// Official college homepage «3D ТУР КИПФИН»; verified November2026. External browser, not an embedded map.
export const CAMPUS_TOUR_URL = 'https://tour.panoee.net/65e08e217a73f2feff4db099/65e08e717a73f212cb4db0ac';
export function campusTourLink() {
  const a = document.createElement('a');
  a.className = 'btn btn--tonal campus-tour'; a.href = CAMPUS_TOUR_URL;
  a.target = '_blank'; a.rel = 'noopener noreferrer';
  a.textContent = '3D-тур КИПФИН ↗'; a.setAttribute('aria-label', '3D-тур КИПФИН на официальном сайте колледжа — откроется в браузере');
  return a;
}

// 3D-тур помогает найти аудиторию, поэтому в окне занятия он только у очных занятий:
// есть аудитория и занятие не дистанционное.
export function showsCampusTour(event) {
  if (!event || event.is_remote) return false;
  return Boolean(event.room_id || event.room_ids?.length || event.room_name);
}
