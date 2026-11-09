import { usage } from './usage.js';
import { h } from './ui.js';
import { campusTourLink } from './campus-tour.js';
export function privacySection() {
  const toggle = h('button', { type:'button', class:'switch', role:'switch', 'aria-label':'Анонимная статистика и технические ошибки', 'aria-checked':String(usage?.consent() || false) }, h('span',{class:'switch-thumb'}));
  const hint = h('p', {class:'field-hint',id:'usage-privacy-hint'}, 'Выключено по умолчанию. Только счётчики и тип/файл/строка ошибки: без идентификаторов, текста поиска, сообщений ошибок и стека. Хранение 30 дней.');
  toggle.setAttribute('aria-describedby','usage-privacy-hint');
  toggle.onclick = () => { const on = usage.setConsent(!usage.consent()); toggle.setAttribute('aria-checked',String(on)); };
  return h('section',{class:'sheet-section',dataset:{usageSettings:''}},h('h3',{},'Конфиденциальность'),
    h('div',{class:'setting-row'},h('span',{class:'setting-row-label'},'Анонимная статистика и технические ошибки'),toggle),hint);
}
export function widgetSection() {
  const native = window.Capacitor?.Plugins?.ItcNative;
  if (!window.Capacitor?.isNativePlatform?.() || !native?.pinWidget) return null;
  const message = h('p',{class:'field-hint',role:'status'},'Избранные кружки, руководители и аудитории. Если избранного нет — всё расписание. На подписки и уведомления фильтр виджета не влияет.');
  const pin = (kind,label) => h('button',{type:'button',class:'btn btn--tonal',onclick:async()=>{
    try { const result=await native.pinWidget({kind}); message.textContent=result?.requested?'Подтвердите добавление в системном окне лаунчера.':'Зажмите рабочий стол → Виджеты → KipClub.'; }
    catch { message.textContent='Не удалось открыть лаунчер. Зажмите рабочий стол → Виджеты → KipClub.'; }
  }},label);
  return h('section',{class:'sheet-section',dataset:{widgetSettings:''}},h('h3',{},'Виджеты на рабочий стол'),message,h('div',{class:'sheet-actions'},pin('next','Следующее занятие'),pin('today','Сегодня')));
}


export function mountFinalSettings(place,tourPlace) { place.replaceChildren(...[widgetSection(),privacySection()].filter(Boolean)); tourPlace.replaceChildren(campusTourLink()); }
