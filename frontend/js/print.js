// 'use strict';
import { getSchedule } from './api.js';
import { 
    DAY_NAMES, parseDate, dateKey, addDays, 
    monday, moscowToday, formatDate, minutes 
} from './schedule-dates.js';

const $ = selector => document.querySelector(selector);

const WEEK_MIN = '2000-01-03';
const WEEK_MAX = '2100-12-27';

const weekNode = $('.print-schedule-week');
const weekCaptionNode = $('.schedule-week-caption');
const nextButton = $('#next-button');
const prevButton = $('#prev-button');
const printButton = $('#print-button');

// To prevent stale api requests overwriting new ones
// Need to increment id and store the local (to function) copy to compare.
// No match -> data is stale -> not needed.
let requestId = 0;

const today = moscowToday();
const weekStart = monday(today);

// Centralized state struct
const state = { 
    weekStart: weekStart,
    weekEnd: addDays(weekStart, 5),
    events: [],
    phase: 'loading',
    error: ''
};

const statusNames = {
    scheduled: 'По расписанию',
    moved: 'Перенос',
    cancelled: 'Отменено'
};

// WTF
function safeEvents(data) {
    const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!Array.isArray(data) || data.some(event => !event || typeof event.event_id !== 'string'
        || !Number.isInteger(event.club_id) || event.club_id <= 0 || !parseDate(event.date)
        || !timePattern.test(event.start_time) || !timePattern.test(event.end_time)
        || minutes(event.start_time) >= minutes(event.end_time)
        || !['club_name', 'leader_name', 'room_name', 'category_name'].every(key => typeof event[key] === 'string')
        || !Object.hasOwn(statusNames, event.status)
        || !['leader_names', 'room_names'].every(key => 
        {
            const res = (event[key] === undefined) || (Array.isArray(event[key]) && event[key].every(item => typeof item === 'string'));
            return res;
        })))
    {
        throw new Error('Сервер вернул расписание в неожиданном формате. Попробуйте обновить данные.');
    }
    const first = dateKey(state.weekStart);
    const last = dateKey(state.weekEnd);
    return data.filter(event => event.date >= first && event.date <= last);
}

async function loadSchedule() {
    const id = ++requestId;
    state.phase = 'loading';
    state.error = '';
    render();
    try {
        const data = await getSchedule(dateKey(state.weekStart));
        if (id !== requestId) {
            return;
        }
        state.events = safeEvents(data);
        state.phase = 'ready';
    } catch (error) {
        if (id !== requestId) {
            return;
        }
        state.phase = 'error';
        state.error = error.message;
    }
    render();
}

function node(tag, className, text = '') {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
}

function render() {
    weekNode.replaceChildren(); // clears child nodes
    if (state.phase === 'loading') {
        renderLoading();
    } else if (state.phase === 'ready') {
        renderSchedule();
    } else {
        renderError();
    }
}

function renderLoading() {
    weekNode.append(node('h3', 'print-schedule-loading', 'Загрузка данных...'));
}

function renderError() {
    weekNode.append(node('h1', 'print-schedule-error', state.error));
}

function renderSchedule() {
    // Data is already sorted by (item["date"], item["start_time"], item["club_name"])
    let j = 0;
    // Outer loop for weekdays, inner for state.events array -> O(i+j)
    for (let i = 0; i < 6; i++) {
        const dayStart = j;
        const date = addDays(state.weekStart, i);
        const key = dateKey(date);
        const daySchedule = node('div', 'print-schedule-day');
        daySchedule.append(node('h3', '', `${DAY_NAMES[i]}, ${formatDate(date)}`));
        while ((j < state.events.length) && (state.events[j].date === key)) {
            daySchedule.append(assembleEvent(state.events[j]));
            j++;
        }   
        if (j === dayStart) {
            daySchedule.append(node('p', 'print-schedule-empty', 'Занятий нет'));
        }
        weekNode.append(daySchedule);
    }
}

function assembleEvent(event) {
    console.log(event);
    const eventNode = node('div', 'print-schedule-lesson');
    const timeNode = node('span', 'ps-lesson-time');
    const leftColumn = node('div', 'print-schedule-lesson-left');
    const midColumn = node('div', 'print-schedule-lesson-mid');
    const rightColumn = node('div', 'print-schedule-lesson-right');
    timeNode.append(
        node('span', 'ps-lesson-time-start', event.start_time),
        node('span', 'ps-lesson-time-end', event.end_time)
    );
    const lessonNameNode = node('strong', 'ps-lesson-name', event.club_name);
    const lessonRoomNode = node(
        'span', 
        'ps-lesson-room',
        (event.room_names.length > 1) 
            ? event.room_names.join(', ') 
            : event.room_name || 'Аудитория не указана'
    );
    const lessonLeaderNode = node(
        'span', 
        'ps-lesson-leader', 
        (event.leader_names.length > 1) 
            ? event.leader_names.join(', ') 
            : event.leader_name || 'Преподаватель неизвестен'
    );
    
    if (event.status === 'cancelled') {
        lessonNameNode.classList.add('crossed-out');
        lessonRoomNode.classList.add('crossed-out');
        lessonLeaderNode.classList.add('crossed-out');
        timeNode.classList.add('crossed-out');
    }

    leftColumn.append(timeNode);
    midColumn.append(lessonNameNode);
    midColumn.append(lessonRoomNode);
    rightColumn.append(lessonLeaderNode);
    
    if (event.status === 'cancelled') {
        leftColumn.append(node('span', 'ps-lesson-status', statusNames[event.status]));
    } else if (event.status === 'moved') {
        leftColumn.append(node(
            'span', 'ps-lesson-status', 
            `${statusNames[event.status]} c ${dateHuman(new Date(event.original_date))}`
        ));
    }
    eventNode.append(leftColumn, midColumn, rightColumn);
    return eventNode;
}

function dateHuman(date) {
    return `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()}`;
}

function updateToolbar() {
    weekCaptionNode.textContent = `${dateHuman(state.weekStart)} — ${dateHuman(state.weekEnd)}`;
}

async function loadWeek(date) {
    const weekStart = monday(date);
    if (dateKey(weekStart) < WEEK_MIN || dateKey(weekStart) > WEEK_MAX) {
        return;
    }
    state.weekStart = weekStart;
    state.weekEnd = addDays(weekStart, 5);

    updateToolbar();
    await loadSchedule();
}

prevButton.addEventListener('click', () => { loadWeek(addDays(state.weekStart, -7)); });
nextButton.addEventListener('click', () => { loadWeek(addDays(state.weekStart, 7)); });
printButton.addEventListener('click', () => { window.print(); }); 

updateToolbar();
loadSchedule();
