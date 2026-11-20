// «Статистика» (GET /api/admin/stats/report): восемь блоков, графики на SVG без библиотек, CSV по каждому блоку.
// Только обезличенные агрегаты: ни текстов отзывов, ни идентификаторов установок, ни IP.
import { h, toast } from '../../ui.js';
import { getStatsReport, getStatsCsv } from '../api.js';
import { pageHeader, loading } from '../kit.js';

const NS = 'http://www.w3.org/2000/svg';
const PLATFORM = { web: 'Браузер', pwa: 'PWA', ios: 'iPhone', android: 'Android' };
const METRIC = {
  install_banner: 'Показ плашки', install_prompt: 'Окно установки', install_accept: 'Согласие', installed: 'Установлено', standalone_open: 'Запуск с экрана',
  ios_guide_open: 'Инструкция', ios_guide_step: 'Шаги', ios_first_standalone: 'Первый запуск с экрана «Домой»',
  apk_page: 'Страница APK', apk_download: 'Нажали «Скачать»', apk_download_server: 'Сервер отдал файл', apk_first_run: 'Первый запуск',
  screen_view: 'Экраны', schedule_view: 'Расписание', schedule_nav: 'Переходы по дням', search_open: 'Поиск', search_pick: 'Выбор из поиска',
  search_abandon: 'Поиск без выбора', search_results: 'Результаты поиска', filter_apply: 'Фильтры', calendar_export: 'В календарь', calendar_fail: 'Сбой календаря',
  tour_open: '3D-тур', share: 'Поделиться', print: 'Печать', offline_open: 'Офлайн-страница', offline_view_stale: 'Расписание из кэша', fav_add: 'В избранное',
  fav_remove: 'Из избранного', app_open: 'Запуски', app_resume: 'Возвраты', load_source: 'Источник загрузки',
  push_shown: 'Показано', push_open: 'Открыто', push_dismiss: 'Смахнули', push_permission: 'Разрешение', push_subscribe: 'Подписались', push_unsubscribe: 'Отписались',
  fb_prompt_shown: 'Показов карточки', fb_prompt_snooze: '«Не сейчас»', fb_prompt_dismiss: '«Не надо»', fb_form_open: 'Открыли форму', fb_sent: 'Отправили',
};
const DIM = {
  none: 'всего', home: 'главная', week: 'неделя', day: 'день', club: 'кружок', clubs: 'каталог', settings: 'настройки', install: 'установка', print: 'печать',
  offline: 'офлайн', whats_new: '«Что нового»', today: 'сегодня', tomorrow: 'завтра', day_other: 'другой день', week_this: 'эта неделя', week_next: 'следующая неделя',
  week_other: 'другая неделя', swipe: 'свайп', tap: 'нажатие', datepicker: 'выбор даты', category: 'направление', room: 'аудитория', leader: 'руководитель',
  one: 'одно занятие', event: 'из занятия', online: 'в сети', warm: 'возврат', cache: 'из кэша', network: 'из сети', granted: 'разрешили', denied: 'запретили',
  default: 'не ответили', web: 'веб', ios: 'iPhone', fcm: 'Android', android: 'Android', prompt_usage: 'после использования', prompt_update: 'после обновления',
  prompt_error: 'после ошибки', shake: 'встряхивание', error: 'экран ошибки', d0: 'сегодняшний', d1: 'вчерашний', d2_7: '2..7 дней', d8p: 'старше недели',
  webview: 'WebView', ui: 'интерфейс', net: 'сеть', storage: 'хранилище', few: '2..5', many: '6 и больше', other: 'другое',
};
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const PERF = { lcp: 'Отрисовка (LCP)', inp: 'Отклик (INP)', cls: 'Сдвиги (CLS)', ttfb: 'Ответ сервера', fcp: 'Первый кадр', ttfs: 'До расписания' };
const label = (map, key) => map[key] || key;
const num = n => (n ?? 0).toLocaleString('ru-RU');
const pct = (a, b) => (b ? `${Math.round((a / b) * 100)} %` : 'нет данных');
const svg = (tag, attrs = {}, ...kids) => { const el = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); el.append(...kids); return el; };

function table(head, rows, empty = 'Пока нет данных.') {
  if (!rows.length) return h('p', { class: 'field-hint' }, empty);
  return h('div', { class: 'table-wrap' }, h('table', { class: 'users-table stats-table' },
    h('thead', {}, h('tr', {}, head.map(t => h('th', { scope: 'col' }, t)))), h('tbody', {}, rows.map(r => h('tr', {}, r.map((c, i) => i ? h('td', {}, String(c)) : h('th', { scope: 'row' }, String(c))))))));
}

function lineChart(series, keys, { height = 160 } = {}) {
  const width = 640, pad = 28, max = Math.max(1, ...series.flatMap(p => keys.map(([k]) => p[k] || 0)));
  const x = i => pad + (series.length < 2 ? 0 : (i * (width - pad * 2)) / (series.length - 1));
  const y = v => height - 20 - (v / max) * (height - 36);
  const chart = svg('svg', { viewBox: `0 0 ${width} ${height}`, class: 'stats-chart', role: 'img', 'aria-label': keys.map(([, t]) => t).join(', ') + ' по дням' });
  for (const t of [0, .5, 1]) chart.append(svg('line', { x1: pad, x2: width - pad, y1: y(max * t), y2: y(max * t), class: 'stats-grid' }),
    svg('text', { x: 2, y: y(max * t) + 4, class: 'stats-axis' }, String(Math.round(max * t))));
  keys.forEach(([k, , cls]) => chart.append(svg('polyline', { points: series.map((p, i) => `${x(i).toFixed(1)},${y(p[k] || 0).toFixed(1)}`).join(' '), class: `stats-line ${cls}` })));
  if (series.length) {
    chart.append(svg('text', { x: pad, y: height - 4, class: 'stats-axis' }, series[0].day.slice(5).split('-').reverse().join('.')),
      svg('text', { x: width - pad, y: height - 4, class: 'stats-axis', 'text-anchor': 'end' }, series.at(-1).day.slice(5).split('-').reverse().join('.')));
  }
  return h('figure', { class: 'stats-figure' }, chart, h('figcaption', { class: 'stats-legend' }, keys.map(([, t, cls]) => h('span', { class: `stats-key ${cls}` }, t))));
}

function bars(items, { total } = {}) {
  const max = Math.max(1, ...items.map(i => i.count));
  if (!items.length) return h('p', { class: 'field-hint' }, 'Пока нет данных.');
  return h('ul', { class: 'stats-bars' }, items.map(i => h('li', {},
    h('span', { class: 'stats-bar-label' }, i.label), h('span', { class: 'stats-bar-track' }, h('span', { class: 'stats-bar-fill', style: `width:${Math.max(2, (i.count / max) * 100)}%` })),
    h('span', { class: 'stats-bar-value' }, num(i.count) + (total ? ` · ${pct(i.count, total)}` : '')))));
}

function block(id, title, days, ...content) {
  const csv = h('button', { type: 'button', class: 'btn btn--tonal btn--small', 'aria-label': `Скачать CSV: ${title}` }, 'CSV');
  csv.addEventListener('click', async () => {
    csv.disabled = true;
    try {
      const blob = await getStatsCsv(id, days);
      const url = URL.createObjectURL(blob);
      const a = h('a', { href: url, download: `kipclub-stats-${id}.csv` }); document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { toast(e?.message || 'Не удалось скачать CSV'); } finally { csv.disabled = false; }
  });
  return h('section', { class: 'card stats-block', id: `stats-${id}`, dataset: { statsBlock: id } }, h('div', { class: 'stats-head' }, h('h2', {}, title), csv), ...content);
}

const fig = (value, text) => h('div', { class: 'users-fig' }, h('strong', {}, value), h('span', {}, text));

function users(d, days) {
  const t = d.today;
  return block('users', 'Пользователи', days,
    h('div', { class: 'users-figs' }, fig(num(t.dau), 'за сегодня'), fig(num(t.wau), 'за 7 дней'), fig(num(t.mau), 'за 30 дней'),
      fig(d.stickiness == null ? 'нет данных' : `${Math.round(d.stickiness * 100)} %`, '«залипание» DAU/MAU')),
    lineChart(d.series, [['dau', 'За день', 'is-dau'], ['wau', 'За 7 дней', 'is-wau'], ['mau', 'За 30 дней', 'is-mau']]),
    table(['Сегодня по платформам', 'Активны'], Object.entries(t.by_platform || {}).map(([p, n]) => [label(PLATFORM, p), num(n)])),
    h('p', { class: 'field-hint' }, 'Считаются установки, где включена анонимная статистика. Один человек с телефоном и компьютером считается дважды.'));
}

function retention(d, days) {
  const width = Math.max(1, ...d.cohorts.map(c => c.weeks.length));
  const head = ['Неделя первого запуска', 'Установок', ...Array.from({ length: Math.min(width, 9) }, (_, i) => (i ? `Неделя ${i}` : 'Неделя 0'))];
  const rows = d.cohorts.map(c => [c.cohort_week.split('-').reverse().join('.'), num(c.size), ...c.weeks.slice(0, 9).map(n => pct(n, c.size))]);
  const day = k => d.days[k]?.rate == null ? 'нет данных' : `${Math.round(d.days[k].rate * 100)} % из ${d.days[k].cohort}`;
  return block('retention', 'Удержание', days,
    h('div', { class: 'users-figs' }, fig(day('d1'), 'вернулись на 2-й день (D1)'), fig(day('d7'), 'через неделю (D7)'), fig(day('d30'), 'через месяц (D30)')),
    table(head, rows, 'Когорты появятся через неделю после выкатки.'));
}

function versions(d, days) {
  const latest = d.latest;
  const last = d.series.at(-1)?.counts || {};
  const total = Object.values(last).reduce((a, b) => a + b, 0);
  const width = 640, height = 120, n = d.series.length, bw = n ? (width - 8) / n : 0;
  const palette = ['v0', 'v1', 'v2', 'v3', 'v4'];
  const top = [...d.versions].reverse().slice(0, 5);
  const chart = svg('svg', { viewBox: `0 0 ${width} ${height}`, class: 'stats-chart', role: 'img', 'aria-label': 'Доля версий по дням' });
  d.series.forEach((p, i) => {
    const sum = Object.values(p.counts).reduce((a, b) => a + b, 0) || 1; let y = height;
    top.forEach((v, k) => { const hgt = ((p.counts[v] || 0) / sum) * (height - 4); y -= hgt; chart.append(svg('rect', { x: 4 + i * bw, y, width: Math.max(1, bw - 1), height: hgt, class: `stats-ver ${palette[k]}` })); });
  });
  return block('versions', 'Версии', days,
    h('div', { class: 'users-figs' }, fig(latest || 'нет данных', 'последняя версия'), fig(num(d.on_old), `ещё на старых${d.on_old_share == null ? '' : ` (${Math.round(d.on_old_share * 100)} %)`}`)),
    n ? h('figure', { class: 'stats-figure' }, chart, h('figcaption', { class: 'stats-legend' }, top.map((v, k) => h('span', { class: `stats-key stats-ver ${palette[k]}` }, v)))) : '',
    table(['Версия', 'Активны в последний день', 'Доля'], Object.entries(last).sort((a, b) => b[1] - a[1]).map(([v, c]) => [v, num(c), pct(c, total)])));
}

function funnels(d, days) {
  const one = (title, steps) => h('div', { class: 'stats-funnel' }, h('h3', {}, title),
    bars(steps.map(s => ({ label: label(METRIC, s.metric), count: s.count })), { total: steps[0]?.count }));
  return block('funnels', 'Установка', days, one('PWA (Android и компьютер)', d.pwa), one('iPhone', d.ios), one('Android APK', d.apk),
    h('p', { class: 'field-hint' }, 'Доли считаются от первого шага. «Сервер отдал файл» считает сам сервер, без выключателя и без данных о человеке.'));
}

function usage(d, days) {
  const ev = k => (d.events[k] || []).map(e => ({ label: label(DIM, e.dim), count: e.count }));
  const sum = k => (d.events[k] || []).reduce((a, e) => a + e.count, 0);
  const weekdays = d.weekdays.map((c, i) => ({ label: WEEKDAYS[i], count: c }));
  return block('usage', 'Использование', days,
    h('div', { class: 'stats-cols' },
      h('div', {}, h('h3', {}, 'Экраны'), bars(ev('screen_view'))),
      h('div', {}, h('h3', {}, 'Что смотрят в расписании'), bars(ev('schedule_view'))),
      h('div', {}, h('h3', {}, 'Дни недели'), bars(weekdays)),
      h('div', {}, h('h3', {}, 'Популярные кружки'), bars(d.top_clubs.map(c => ({ label: c.name, count: c.count }))))),
    table(['Действие', 'Сколько раз'], ['search_open', 'search_pick', 'search_abandon', 'filter_apply', 'calendar_export', 'calendar_fail', 'tour_open', 'share', 'print',
      'offline_open', 'fav_add', 'fav_remove'].map(k => [label(METRIC, k), num(sum(k))])),
    h('h3', {}, 'Переходы по дням'), bars(ev('schedule_nav')), h('h3', {}, 'Фильтры'), bars(ev('filter_apply')));
}

function push(d, days) {
  const ch = { web: 'Веб', ios: 'iPhone', fcm: 'Android' };
  return block('push', 'Пуши', days,
    table(['Канал', 'Отправлено', 'Ошибок', 'Показано', 'Открыто', 'Открыли из показанных'],
      Object.entries(d.channels).map(([c, v]) => [ch[c] || c, v.sent == null ? 'в составе веба' : num(v.sent), v.failed == null ? '' : num(v.failed), num(v.shown), num(v.opened), pct(v.opened, v.shown)])),
    h('h3', {}, 'Разрешения и подписки'),
    table(['Событие', 'Подробности'], Object.entries(d.client).map(([m, dims]) => [label(METRIC, m), Object.entries(dims).map(([k, n]) => `${label(DIM, k)}: ${num(n)}`).join(', ')])),
    h('h3', {}, 'Последние рассылки'),
    table(['Рассылка', 'Веб', 'Android', 'Показано и открыто'], d.broadcasts.map(b => [`${b.title} · ${b.created_at.slice(8, 10)}.${b.created_at.slice(5, 7)}`, num(b.web_sent), num(b.fcm_sent),
      Object.entries(b.receipts).map(([c, r]) => `${label(DIM, c)}: ${r.shown} / ${r.opened}`).join(', ') || 'нет подтверждений'])),
    h('p', { class: 'field-hint' }, 'Ответ Web Push и FCM не доказывает доставку. Показы и открытия приходят только от клиентов с включённой статистикой и в сети.'));
}

function quality(d, days) {
  const p = d.bucket_labels, c = d.cls_labels;
  return block('quality', 'Качество', days,
    h('div', { class: 'users-figs' }, fig(num(Object.values(d.errors_by_version).reduce((a, b) => a + b, 0)), 'JS-ошибок'),
      fig(num(d.new_after_release.length), `новых в ${d.latest || 'последней версии'}`), fig(num(d.api_errors.reduce((a, e) => a + e.count, 0)), 'ошибок API'),
      fig(num(d.native_crashes.reduce((a, e) => a + e.count, 0)), 'падений APK')),
    h('h3', {}, 'Скорость, 75-й процентиль'),
    table(['Платформа', 'Метрика', 'Медиана', '75 %', 'Замеров'], d.perf.map(r => [label(PLATFORM, r.platform), label(PERF, r.metric),
      (r.metric === 'cls' ? c : p)[r.p50] || 'нет', (r.metric === 'cls' ? c : p)[r.p75] || 'нет', num(r.samples)])),
    h('h3', {}, 'Ошибки по версиям'), table(['Версия', 'Ошибок'], Object.entries(d.errors_by_version).map(([v, n]) => [v, num(n)])),
    h('h3', {}, 'Новые после релиза'), table(['Тип', 'Файл и строка', 'Сколько'], d.new_after_release.map(e => [e.code, `${e.source}:${e.line}`, num(e.count)]), 'Новых ошибок нет.'),
    h('h3', {}, 'Ошибки API'), table(['Раздел и класс ответа', 'Сколько'], d.api_errors.map(e => [e.dim.replace('_', ' · '), num(e.count)])),
    h('h3', {}, 'Падения APK'), table(['Подсистема', 'Сколько'], d.native_crashes.map(e => [label(DIM, e.dim), num(e.count)]), 'Падений нет.'));
}

function feedback(d, days) {
  const avg = v => (v?.avg == null ? 'нет оценок' : `${String(v.avg).replace('.', ',')} из 5`);
  const dist = v => ['1', '2', '3', '4', '5'].map(k => v.dist?.[k] || 0).join(' / ');
  return block('feedback', 'Отзывы', days,
    h('div', { class: 'users-figs' }, fig(avg(d.overall), `средняя оценка, ${num(d.overall.count)} оценок`),
      fig(num(Object.values(d.prompts.fb_sent || {}).reduce((a, b) => a + b, 0)), 'отправлено сообщений')),
    h('h3', {}, 'По версиям'), table(['Версия', 'Средняя', 'Оценок', '1 / 2 / 3 / 4 / 5'], Object.entries(d.by_version).map(([v, r]) => [v, avg(r), num(r.count), dist(r)])),
    h('h3', {}, 'По платформам'), table(['Платформа', 'Средняя', 'Оценок', '1 / 2 / 3 / 4 / 5'], Object.entries(d.by_platform).map(([v, r]) => [label(PLATFORM, v), avg(r), num(r.count), dist(r)])),
    h('h3', {}, 'Карточка «Как тебе KipClub?» и форма'),
    table(['Событие', 'Откуда'], Object.entries(d.prompts).map(([m, dims]) => [label(METRIC, m), Object.entries(dims).map(([k, n]) => `${label(DIM, k)}: ${num(n)}`).join(', ')])),
    h('p', { class: 'field-hint' }, 'Только цифры. Тексты сообщений здесь не показываются, их читают разработчики.'));
}

export async function mount(root, { signal }) {
  let days = 90;
  const periods = h('div', { class: 'segmented stats-period', role: 'radiogroup', 'aria-label': 'Период' },
    [[7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([v, t]) => {
      const input = h('input', { type: 'radio', name: 'stats-days', value: String(v), checked: v === days });
      input.addEventListener('change', () => { days = v; load(); });
      return h('label', {}, input, h('span', {}, t));
    }));
  const body = h('div', { class: 'stats-body' }, loading());
  root.replaceChildren(pageHeader('Статистика'), h('p', { class: 'field-hint stats-intro' },
    'Обезличенные данные (docs/privacy.md): без имён, контактов, IP и текстов. Подробные дни хранятся 90 дней, дальше только итоги по месяцам.'), periods, body);
  root.querySelector('#view-title')?.focus({ preventScroll: true });
  async function load() {
    body.replaceChildren(loading());
    const data = await getStatsReport(days, { signal });
    body.replaceChildren(h('p', { class: 'field-hint' }, `С ${data.since.split('-').reverse().join('.')} по ${data.today.split('-').reverse().join('.')}, МСК.`),
      users(data.users, days), retention(data.retention, days), versions(data.versions, days), funnels(data.funnels, days),
      usage(data.usage, days), push(data.push, days), quality(data.quality, days), feedback(data.feedback, days));
  }
  await load();
}
