// Не заменяем осознанно выбранный цвет направления; для общего серого
// справочника используем устойчивый цвет кружка на всех экранах.
const CLUB_COLORS = [
  '#e45252', '#247bc1', '#a558c5', '#168773', '#c46a1b', '#4864cc',
  '#c14382', '#608d20', '#a25b35', '#00889e', '#c44938', '#7970b8',
  '#39805d', '#bd8020', '#7f519d', '#d35f60', '#0080aa', '#a84665',
  '#6b812c', '#b35d9a', '#3f76a8', '#bd6935', '#42927c', '#9a5c58',
];

export function clubColor(clubId, categoryColor, categoryName = '') {
  const color = String(categoryColor || '').toLowerCase();
  const placeholder = !/^#[\da-f]{6}$/.test(color) || ['#64748b', '#606963'].includes(color)
    || String(categoryName).trim().toLowerCase() === 'без направления';
  if (!placeholder) return color;
  const id = Number(clubId);
  return CLUB_COLORS[(Number.isSafeInteger(id) && id > 0 ? id - 1 : 0) % CLUB_COLORS.length];
}
