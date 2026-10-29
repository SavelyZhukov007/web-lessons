'use strict';

import { getSchedule } from './api.js';
import { DAY_NAMES, DAY_SHORT, parseDate, dateKey, addDays, monday, moscowToday, formatDate, minutes, eventGroups } from './schedule-dates.js';

const $ = selector => document.querySelector(selector);

const fields = { 
    category_id: $('#category'),
    weekday: $('#weekday'),
    leader_id: $('#leader'),
    room_id: $('#room')
};

const content = $('#content');

const state = { 
    week: monday(today),
    day: Math.min((today.getDay() + 6) % 7, 5),
    view: 'grid',
    filtersOpen: false,
    events: [],
    phase: 'loading',
    error: ''
};

const statusNames = {
    scheduled: 'По расписанию',
    moved: 'Перенос',
    cancelled: 'Отменено'
};

function showWeek(date) {
    const week = monday(date);
    if (dateKey(week) < WEEK_MIN || dateKey(week) > WEEK_MAX) return;
    state.week = week;
    loadSchedule();
}

function filters() {
  return Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value.trim()]));
}


async function loadSchedule() {
    const request = scheduleRequest.begin();
    state.phase = 'loading';
    state.events = [];
    try {
        const data = await getSchedule(dateKey(state.week), filters(), { signal: request.signal });
        if (!request.isCurrent()) return;
        state.events = safeEvents(data);
        state.phase = 'ready';
    } catch (error) {
        if (!request.isCurrent() || error.name === 'AbortError') return;
        state.phase = 'error';
        state.error = error.message;
    }
    render();
}


function render() {
    updateControls();
    content.replaceChildren();
    content.setAttribute('aria-busy', String(state.phase === 'loading'));
    if (state.phase === 'loading') {
        $('#result-status').textContent = 'Загружаем расписание…';
        content.append(emptyState('Загружаем занятия', 'Получаем актуальное расписание с сервера.'));
        content.firstElementChild.classList.add('is-loading');
        return;
    }
    if (state.phase === 'error') {
        $('#result-status').textContent = 'Расписание не загружено';
        content.append(emptyState('Не получилось загрузить расписание', state.error, { label: 'Повторить попытку', run: loadSchedule }));
        return;
    }
    const days = mobile.matches ? [state.day] : visibleDays();
    const events = state.events.filter(event => days.some(day => event.date === dateKey(addDays(state.week, day))));
    const active = events.filter(event => event.status !== 'cancelled').length;
    const cancelled = events.length - active;
    $('#result-status').textContent = `${mobile.matches ? 'За день' : 'За выбранные дни'}: ${active} · отменено: ${cancelled}${hasFilters() ? ' · фильтры включены' : ''}`;
    if (events.length === 0) {
        content.append(emptyState(hasFilters() ? 'Ничего не нашлось' : 'Занятий пока нет', hasFilters() ? 'Попробуй другое сочетание фильтров или сбрось их.' : 'Выбери другой день или неделю. Здесь появятся занятия, добавленные в расписание.', hasFilters() ? { label: 'Сбросить фильтры', run: resetFilters } : undefined));
    } else renderList(events, days);
}
