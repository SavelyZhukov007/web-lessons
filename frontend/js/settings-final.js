import { usage } from './usage.js';
import { h } from './ui.js';
import { campusTourLink } from './campus-tour.js';
export const SHAKE_KEY = 'kc.shakeFeedback';
export const shakeEnabled = () => { try { return localStorage.getItem(SHAKE_KEY) !== '0'; } catch { return true; } };
function switchRow(label, on, hintId, onToggle) {
  const toggle = h('button', { type:'button', class:'switch', role:'switch', 'aria-label':label, 'aria-checked':String(on), 'aria-describedby':hintId }, h('span',{class:'switch-thumb'}));
  toggle.onclick = () => toggle.setAttribute('aria-checked', String(onToggle(toggle.getAttribute('aria-checked') !== 'true')));
  return h('div',{class:'setting-row'},h('span',{class:'setting-row-label'},label),toggle);
}
export function privacySection() {
  const native = window.Capacitor?.isNativePlatform?.();
  const rows = [switchRow('Анонимная статистика', usage?.enabled() ?? true, 'usage-privacy-hint', on => usage.setEnabled(on)),
    h('p', {class:'field-hint',id:'usage-privacy-hint'}, 'Помогает понять, что в KipClub работает, а что нет. Только счётчики: какие экраны открывают, ошибки, скорость, версия. Без имён, контактов, IP-адресов и текста поиска. Подробные дни хранятся 90 дней, дальше остаются только итоги по месяцам. Выключи, и KipClub перестанет отправлять статистику.')];
  if (native) {
    rows.push(switchRow('Встряхнуть, чтобы сообщить об ошибке', shakeEnabled(), 'shake-hint', on => {
      try { localStorage.setItem(SHAKE_KEY, on ? '1' : '0'); } catch { /* ignore */ }
      window.Capacitor?.Plugins?.ItcNative?.setShake?.({ enabled: on }).catch?.(() => {});
      return on;
    }), h('p', {class:'field-hint',id:'shake-hint'}, 'Встряхни телефон, и откроется форма с типом «Ошибка».'));
  }
  return h('section',{class:'sheet-section',dataset:{usageSettings:''}},h('h3',{},'Конфиденциальность'),...rows);
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
