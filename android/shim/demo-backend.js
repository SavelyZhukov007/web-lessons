/* ДЕМО/ОФЛАЙН-режим (сборка `python server.py build android --demo`).
 * Подключается ПЕРВЫМ скриптом вместо app-shim.js. Перехватывает fetch('/api/...') и отвечает из локального
 * «бэкенда» в localStorage (те же эндпоинты и форматы, что у FastAPI). Сеть не нужна. Админ вошёл автоматически.
 * window.DemoBackend.reset() — пересоздать случайные данные. */
(function () {
  'use strict';
  // подключён тестовый сервер (Настройки → «Подключить тестовый сервер»): работаем с настоящим API, демо выключено
  try { if (localStorage.getItem('clubs.serverUrl')) { window.APP_DEMO_BUILD = true; return; } } catch (e) {}
  window.APP_DEMO_BUILD = true;
  var KEY = 'itc.demo.db.v1';
  var DAY = 86400000;

  // ---------- утилиты дат (локальные, без часовых поясов)
  function iso(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function parse(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function addDays(d, n) { var x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); return x; }
  function isoWeekday(d) { return d.getDay() === 0 ? 7 : d.getDay(); }
  function monday(d) { return addDays(d, 1 - isoWeekday(d)); }

  // ---------- генерация данных
  function rng(seed) { return function () { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }
  function seed() {
    var r = rng((Date.now() ^ 0x5eed) >>> 0);
    var pick = function (a) { return a[Math.floor(r() * a.length)]; };
    var categories = [
      ['Наука и технологии', '#2f6fdf'], ['Творчество', '#c2410c'], ['Спорт', '#15803d'],
      ['Языки', '#7c3aed'], ['Финансы и бизнес', '#b45309'], ['Медиа', '#be185d']
    ].map(function (c, i) { return { id: i + 1, name: c[0], color: c[1] }; });
    var first = ['Анна', 'Ирина', 'Олег', 'Сергей', 'Мария', 'Дмитрий', 'Екатерина', 'Алексей', 'Наталья', 'Павел', 'Ольга', 'Виктор'];
    var mid = { 'Анна': 'Сергеевна', 'Ирина': 'Викторовна', 'Олег': 'Петрович', 'Сергей': 'Александрович', 'Мария': 'Игоревна', 'Дмитрий': 'Андреевич', 'Екатерина': 'Олеговна', 'Алексей': 'Николаевич', 'Наталья': 'Юрьевна', 'Павел': 'Дмитриевич', 'Ольга': 'Михайловна', 'Виктор': 'Иванович' };
    var lastM = ['Смирнов', 'Кузнецов', 'Попов', 'Волков', 'Соколов', 'Лебедев', 'Козлов', 'Новиков', 'Морозов', 'Орлов'];
    var fem = { 'Анна': 1, 'Ирина': 1, 'Мария': 1, 'Екатерина': 1, 'Наталья': 1, 'Ольга': 1 };
    var positions = ['преподаватель информатики', 'педагог дополнительного образования', 'преподаватель экономики', 'руководитель физвоспитания', 'преподаватель английского языка', 'методист', 'преподаватель права'];
    var leaders = first.slice().sort(function () { return r() - 0.5; }).slice(0, 9).map(function (f, i) {
      var l = pick(lastM) + (fem[f] ? 'а' : '');
      return { id: i + 1, name: l + ' ' + f + ' ' + mid[f], position: pick(positions), contact: 'каб. ' + (100 + Math.floor(r() * 320)) + ', ' + ['@', 'tg: @'][i % 2] + 'itc_' + (i + 1) };
    });
    var rooms = [['101', 'Главный корпус', 30], ['204', 'Главный корпус', 25], ['215 (IT-лаборатория)', 'Главный корпус', 16], ['Актовый зал', 'Главный корпус', 120],
      ['Спортзал', 'Спорткомплекс', 60], ['3-12', 'Корпус Б', 20], ['Медиастудия', 'Корпус Б', 12], ['Библиотека', 'Корпус Б', 35]]
      .map(function (x, i) { return { id: i + 1, name: x[0], building: x[1], capacity: x[2] }; });
    var clubDefs = [
      ['Робототехника', 1, 'Собираем и программируем роботов на Arduino, готовимся к WorldSkills.', 3],
      ['Программирование на Python', 1, 'От первых скриптов до телеграм-ботов и анализа данных.', 3],
      ['Кибербезопасность', 1, 'CTF-задачи, сетевые атаки и защита, разбор реальных инцидентов.', 3],
      ['Театральная студия «Маска»', 2, 'Сценическая речь, импровизация, постановка спектакля к весне.', 4],
      ['Вокальный ансамбль', 2, 'Эстрадный вокал и выступления на праздниках колледжа.', 4],
      ['Фотостудия', 6, 'Композиция, свет, обработка; фотоотчёты мероприятий.', 7],
      ['Студенческая газета «ИТС-Вестник»', 6, 'Пишем, редактируем и верстаем выпуски, ведём соцсети.', 7],
      ['Волейбол', 3, 'Тренировки сборной и товарищеские игры с другими колледжами.', 5],
      ['Настольный теннис', 3, 'Для начинающих и продолжающих, внутренний турнир каждый месяц.', 5],
      ['Разговорный английский', 4, 'Speaking club: дебаты, фильмы, подготовка к собеседованиям.', 6],
      ['Финансовая грамотность', 5, 'Личный бюджет, налоги, инвестиции и защита от мошенников.', 2],
      ['Бизнес-инкубатор', 5, 'Придумываем и защищаем стартап-проекты, встречи с предпринимателями.', 8]
    ];
    var clubs = clubDefs.map(function (c, i) { return { id: i + 1, name: c[0], description: c[2], category_id: c[1], leader_id: (i % leaders.length) + 1, is_active: i !== 11 || r() > 0.3 }; });
    var slots = [['14:30', '16:00'], ['15:00', '16:30'], ['16:10', '17:40'], ['16:30', '18:00'], ['17:50', '19:20']];
    var sessions = []; var busy = {};
    clubs.forEach(function (c, i) {
      var n = r() < 0.5 ? 2 : 1; var tries = 0;
      while (n > 0 && tries++ < 40) {
        var wd = 1 + Math.floor(r() * 6); if (wd === 6 && r() < 0.6) continue;
        var s = pick(slots); var room = clubDefs[i][3]; var k = wd + '|' + s[0] + '|' + room;
        // как на сервере: одна аудитория или один руководитель не могут быть заняты дважды в одно время (параллельно — можно в разных)
        if (busy[k] || sessions.some(function (x) { return x.weekday === wd && (x.club_id === c.id || (x.start_time < s[1] && s[0] < x.end_time &&
          (x.room_id === room || clubs[x.club_id - 1].leader_id === c.leader_id))); })) continue;
        busy[k] = 1; sessions.push({ id: sessions.length + 1, club_id: c.id, room_id: room, weekday: wd, start_time: s[0], end_time: s[1] }); n--;
      }
    });
    // «семестр»: исключения в окне от -6 до +8 недель от текущей
    var exceptions = []; var thisMon = monday(new Date());
    var reasons = ['Руководитель на курсах повышения квалификации', 'Аудитория занята под экзамен', 'Праздничный день', 'Болезнь руководителя', 'Мероприятие колледжа'];
    var moveReasons = ['Перенос из-за олимпиады', 'Замена аудитории на время ремонта', 'Перенос по просьбе участников'];
    for (var w = -6; w <= 8; w++) {
      var weekMon = addDays(thisMon, w * 7);
      sessions.forEach(function (s) {
        var x = r(); var od = iso(addDays(weekMon, s.weekday - 1));
        if (x < 0.06) exceptions.push({ id: exceptions.length + 1, session_id: s.id, original_date: od, type: 'cancelled', new_date: null, new_start_time: null, new_end_time: null, new_room_id: null, comment: pick(reasons) });
        else if (x < 0.10) {
          var shift = s.weekday < 6 ? 1 : -1; var sl = pick(slots);
          exceptions.push({ id: exceptions.length + 1, session_id: s.id, original_date: od, type: 'moved', new_date: iso(addDays(parse(od), shift)), new_start_time: sl[0], new_end_time: sl[1], new_room_id: pick(rooms).id, comment: pick(moveReasons) });
        }
      });
    }
    // гарантируем хотя бы одну отмену и один перенос на текущей неделе — для демонстрации
    [['cancelled', 0], ['moved', 1]].forEach(function (t) {
      var s = sessions[t[1] * 3 % sessions.length]; var od = iso(addDays(thisMon, s.weekday - 1));
      if (exceptions.some(function (e) { return e.session_id === s.id && e.original_date === od; })) return;
      var shift = s.weekday < 6 ? 1 : -1;
      exceptions.push(t[0] === 'cancelled'
        ? { id: 0, session_id: s.id, original_date: od, type: 'cancelled', new_date: null, new_start_time: null, new_end_time: null, new_room_id: null, comment: 'Руководитель в командировке' }
        : { id: 0, session_id: s.id, original_date: od, type: 'moved', new_date: iso(addDays(parse(od), shift)), new_start_time: '17:50', new_end_time: '19:20', new_room_id: 2, comment: 'Перенос из-за дня открытых дверей' });
    });
    exceptions.forEach(function (e, i) { e.id = i + 1; });
    var admins = [{ id: 1, login: 'admin', password: 'admin' }, { id: 2, login: 'metodist', password: 'demo1234' }, { id: 3, login: 'zavuch', password: 'demo1234' }];
    var users = ['Иванов Артём, ИС-21', 'Петрова Дарья, ФИН-12', 'Сидоров Никита, ИС-23', 'Ковалёва Алина, ЮР-11', 'Морозов Глеб, ИС-31', 'Фёдорова Полина, ФИН-22']
      .map(function (n, i) { return { id: i + 1, name: n, subscribed_club_ids: [1 + (i * 5) % 12, 1 + (i * 7) % 12] }; });
    return { version: 1, seededAt: new Date().toISOString(), categories: categories, leaders: leaders, rooms: rooms, clubs: clubs, sessions: sessions,
      session_exceptions: exceptions, admins: admins, users: users, push_subscriptions: [], notifications: [] };
  }

  var db;
  function load() {
    try { db = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { db = null; }
    if (!db || db.version !== 1 || !db.seed2) { db = seed(); db.seed2 = 1; save(); } // seed2: демо без пересечений аудиторий/руководителей
    if (!db.attendance) db.attendance = [];
    if (db.attSeeded !== 2) { db.attendance = []; db.nonces = []; db.student_devices = {}; seedAttendance(); db.attSeeded = 2; save(); }
  }
  function save() { localStorage.setItem(KEY, JSON.stringify(db)); }
  load();

  // ---------- HTTP-подобные помощники
  function Http(status, detail) { this.status = status; this.detail = detail; }
  function fail(status, detail) { throw new Http(status, detail); }
  function nextId(list) { return list.reduce(function (m, x) { return Math.max(m, x.id); }, 0) + 1; }
  function byId(list, id, detail) { var x = list.find(function (i) { return i.id === id; }); if (!x) fail(404, detail); return x; }
  function cmp() { var keys = arguments; return function (a, b) { for (var i = 0; i < keys.length; i++) { var k = keys[i]; var x = typeof k === 'function' ? k(a) : a[k]; var y = typeof k === 'function' ? k(b) : b[k]; if (x < y) return -1; if (x > y) return 1; } return 0; }; }
  var CLOCK = /^(?:0[89]|1[0-9]|20):[0-5][0-9]$|^21:00$/;
  var DATE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
  var WD = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
  function v422(msg) { fail(422, [{ msg: msg }]); }
  function str(body, k, req, max) {
    if (!(k in body)) { if (req) v422(k + ': обязательное поле'); return; }
    if (typeof body[k] !== 'string') v422(k + ': ожидается строка');
    body[k] = k === 'description' || k === 'comment' ? body[k] : body[k].trim();
    if ((req === 'name' || k === 'name') && !body[k]) v422('Название не может быть пустым');
    if (body[k].length > (max || 120)) v422(k + ': слишком длинно');
  }
  function int(body, k, req, min, max) {
    if (!(k in body)) { if (req) v422(k + ': обязательное поле'); return; }
    if (!Number.isInteger(body[k]) || body[k] < (min || 1) || (max && body[k] > max)) v422(k + ': некорректное значение');
  }
  function noNull(body) { Object.keys(body).forEach(function (k) { if (body[k] === null) v422('null недопустим: ' + k); }); }
  function only(body, allowed) { Object.keys(body).forEach(function (k) { if (allowed.indexOf(k) < 0) v422('Лишнее поле: ' + k); }); }
  function pickKeys(o, keys) { var r = {}; keys.forEach(function (k) { r[k] = o[k]; }); return r; }

  // ---------- расписание (порт backend/app/services/schedule.py)
  function buildWeek(weekStart) {
    var weekEnd = addDays(weekStart, 6); var ws = iso(weekStart), we = iso(weekEnd);
    var clubs = {}; db.clubs.forEach(function (c) { if (c.is_active) clubs[c.id] = c; });
    var cat = idx(db.categories), lead = idx(db.leaders), room = idx(db.rooms), sess = idx(db.sessions);
    var exc = {}; db.session_exceptions.forEach(function (e) { exc[e.session_id + '|' + e.original_date] = e; });
    function base(s, c) { var k = cat[c.category_id], l = lead[c.leader_id]; return { session_id: s.id, club_id: c.id, club_name: c.name, category_id: k.id, category_name: k.name, category_color: k.color, leader_id: l.id, leader_name: l.name }; }
    var ev = [];
    db.sessions.forEach(function (s) {
      var c = clubs[s.club_id]; if (!c) return;
      var od = iso(addDays(weekStart, s.weekday - 1)); var e = exc[s.id + '|' + od];
      if (!e || e.type === 'cancelled') {
        ev.push(Object.assign(base(s, c), { event_id: s.id + ':' + od, room_id: s.room_id, room_name: room[s.room_id].name, date: od, start_time: s.start_time, end_time: s.end_time, status: e ? 'cancelled' : 'scheduled', original_date: od, comment: e ? e.comment : '' }));
      } else if (e.new_date >= ws && e.new_date <= we) {
        ev.push(Object.assign(base(s, c), { event_id: s.id + ':' + od, room_id: e.new_room_id, room_name: room[e.new_room_id].name, date: e.new_date, start_time: e.new_start_time, end_time: e.new_end_time, status: 'moved', original_date: od, original_start_time: s.start_time, original_end_time: s.end_time, comment: e.comment }));
      }
    });
    db.session_exceptions.forEach(function (e) {
      if (e.type !== 'moved') return;
      if (!(e.new_date >= ws && e.new_date <= we) || (e.original_date >= ws && e.original_date <= we)) return;
      var s = sess[e.session_id]; if (!s) return; var c = clubs[s.club_id]; if (!c) return;
      ev.push(Object.assign(base(s, c), { event_id: s.id + ':' + e.original_date, room_id: e.new_room_id, room_name: room[e.new_room_id].name, date: e.new_date, start_time: e.new_start_time, end_time: e.new_end_time, status: 'moved', original_date: e.original_date, original_start_time: s.start_time, original_end_time: s.end_time, comment: e.comment }));
    });
    return ev.sort(cmp('date', 'start_time', 'club_name'));
  }
  function idx(list) { var m = {}; list.forEach(function (x) { m[x.id] = x; }); return m; }

  // конфликт аудитории/руководителя по еженедельным занятиям (упрощённая версия серверной проверки)
  function sessionConflict(cand, selfId) {
    var club = byId(db.clubs, cand.club_id, 'Кружок не найден');
    var hit = db.sessions.filter(function (s) {
      if (s.id === selfId || s.weekday !== cand.weekday) return false;
      if (!(s.start_time < cand.end_time && cand.start_time < s.end_time)) return false;
      var other = db.clubs.find(function (c) { return c.id === s.club_id; });
      return s.room_id === cand.room_id || (other && other.leader_id === club.leader_id) || s.club_id === cand.club_id;
    });
    if (hit.length) fail(409, { code: 'CONFLICT', message: 'Занятие пересекается с существующим расписанием',
      conflicts: hit.map(function (s) { // поля как у сервера (schedule_conflicts.py): имена кружка, аудитории, руководителя и ближайшая дата
        var c = db.clubs.find(function (x) { return x.id === s.club_id; }) || {}, r = db.rooms.find(function (x) { return x.id === s.room_id; }) || {};
        var l = db.leaders.find(function (x) { return x.id === c.leader_id; }) || {};
        var d = new Date(); d.setDate(d.getDate() + ((s.weekday - (d.getDay() || 7) + 7) % 7));
        var iso = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        return { session_id: s.id, club_id: s.club_id, room_id: s.room_id, weekday: s.weekday, date: iso, start_time: s.start_time, end_time: s.end_time,
          club_name: c.name || 'Кружок', room_name: r.name || 'аудитория не указана', leader_name: l.name || 'руководитель не указан' }; }) });
  }

  // ---------- CRUD
  var ADMIN = { id: 1, login: 'admin' };
  // Демо входит в админку автоматически, пока пользователь явно не нажал «Выйти» (флаг переживает перезапуск приложения).
  var LOGGED_OUT = 'itc.demo.loggedOut';
  function loggedOut() { try { return localStorage.getItem(LOGGED_OUT) !== '0'; } catch (e) { return true; } } // t99: без автовхода — админка только после входа
  function setLoggedOut(v) { try { localStorage.setItem(LOGGED_OUT, v ? '1' : '0'); } catch (e) {} }
  function crudCategories(method, id, body) {
    if (method === 'GET' && id == null) return db.categories.slice().sort(cmp('name', 'id'));
    if (method === 'POST') { only(body, ['name', 'color']); str(body, 'name', 'name'); if (!/^#[0-9a-fA-F]{6}$/.test(body.color || '')) v422('Цвет в формате #RRGGBB'); var x = { id: nextId(db.categories), name: body.name, color: body.color }; db.categories.push(x); return [201, x]; }
    var item = byId(db.categories, id, 'Направление не найдено');
    if (method === 'PATCH') { noNull(body); only(body, ['name', 'color']); str(body, 'name'); if ('color' in body && !/^#[0-9a-fA-F]{6}$/.test(body.color)) v422('Цвет в формате #RRGGBB'); Object.assign(item, body); return item; }
    if (method === 'DELETE') { if (db.clubs.some(function (c) { return c.category_id === id; })) fail(409, 'Нельзя удалить направление, пока к нему привязаны кружки'); db.categories.splice(db.categories.indexOf(item), 1); return [204, null]; }
  }
  function crudLeaders(method, id, body) {
    if (method === 'GET' && id == null) return db.leaders.slice().sort(cmp('name', 'id'));
    var F = ['name', 'position', 'contact'];
    if (method === 'POST') { only(body, F); str(body, 'name', 'name'); str(body, 'position', false, 300); str(body, 'contact', false, 300); var x = { id: nextId(db.leaders), name: body.name, position: body.position || '', contact: body.contact || '' }; db.leaders.push(x); return [201, x]; }
    var item = byId(db.leaders, id, 'Руководитель не найден');
    if (method === 'PATCH') { noNull(body); only(body, F); str(body, 'name'); str(body, 'position', false, 300); str(body, 'contact', false, 300); Object.assign(item, body); return item; }
    if (method === 'DELETE') { if (db.clubs.some(function (c) { return c.leader_id === id; })) fail(409, 'Нельзя удалить руководителя, пока к нему привязаны кружки'); db.leaders.splice(db.leaders.indexOf(item), 1); return [204, null]; }
  }
  function crudRooms(method, id, body) {
    if (method === 'GET' && id == null) return db.rooms.slice().sort(cmp('building', 'name', 'id'));
    var F = ['name', 'building', 'capacity'];
    if (method === 'POST') { only(body, F); str(body, 'name', 'name'); str(body, 'building', false, 300); int(body, 'capacity', true); var x = { id: nextId(db.rooms), name: body.name, building: body.building || '', capacity: body.capacity }; db.rooms.push(x); return [201, x]; }
    var item = byId(db.rooms, id, 'Аудитория не найдена');
    if (method === 'PATCH') { noNull(body); only(body, F); str(body, 'name'); str(body, 'building', false, 300); int(body, 'capacity'); Object.assign(item, body); return item; }
    if (method === 'DELETE') {
      if (db.sessions.some(function (s) { return s.room_id === id; })) fail(409, 'Нельзя удалить аудиторию, пока в ней есть регулярные занятия');
      if (db.session_exceptions.some(function (e) { return e.new_room_id === id; })) fail(409, 'Нельзя удалить аудиторию, пока на неё есть переносы занятий');
      db.rooms.splice(db.rooms.indexOf(item), 1); return [204, null];
    }
  }
  function crudClubs(method, id, body) {
    if (method === 'GET' && id == null) return db.clubs.slice().sort(cmp('name', 'id'));
    var F = ['name', 'description', 'category_id', 'leader_id', 'is_active'];
    function refs(b) { if ('category_id' in b) byId(db.categories, b.category_id, 'Направление не найдено'); if ('leader_id' in b) byId(db.leaders, b.leader_id, 'Руководитель не найден'); if ('is_active' in b && typeof b.is_active !== 'boolean') v422('is_active: ожидается true/false'); }
    if (method === 'POST') { only(body, F); str(body, 'name', 'name'); str(body, 'description', false, 4000); int(body, 'category_id', true); int(body, 'leader_id', true); refs(body);
      var x = { id: nextId(db.clubs), name: body.name, description: body.description || '', category_id: body.category_id, leader_id: body.leader_id, is_active: body.is_active !== false }; db.clubs.push(x); return [201, x]; }
    var item = byId(db.clubs, id, 'Кружок не найден');
    if (method === 'PATCH') { noNull(body); only(body, F); str(body, 'name'); str(body, 'description', false, 4000); int(body, 'category_id'); int(body, 'leader_id'); refs(body); Object.assign(item, body); return item; }
    if (method === 'DELETE') {
      var sids = db.sessions.filter(function (s) { return s.club_id === id; }).map(function (s) { return s.id; });
      db.session_exceptions = db.session_exceptions.filter(function (e) { return sids.indexOf(e.session_id) < 0; });
      db.sessions = db.sessions.filter(function (s) { return s.club_id !== id; });
      db.clubs.splice(db.clubs.indexOf(item), 1); return [204, null];
    }
  }
  function checkSession(b, partial) {
    int(b, 'club_id', !partial); int(b, 'room_id', !partial); int(b, 'weekday', !partial, 1, 6);
    ['start_time', 'end_time'].forEach(function (k) { if (k in b) { if (!CLOCK.test(b[k])) v422('Время в диапазоне 08:00–21:00 (ЧЧ:ММ)'); } else if (!partial) v422(k + ': обязательное поле'); });
    if ('club_id' in b) byId(db.clubs, b.club_id, 'Кружок не найден');
    if ('room_id' in b) byId(db.rooms, b.room_id, 'Аудитория не найдена');
  }
  function crudSessions(method, id, body) {
    if (method === 'GET' && id == null) return db.sessions.slice().sort(cmp('weekday', 'start_time', 'id'));
    var F = ['club_id', 'room_id', 'weekday', 'start_time', 'end_time'];
    if (method === 'POST') { only(body, F); checkSession(body); if (body.start_time >= body.end_time) v422('Начало занятия должно быть раньше конца'); sessionConflict(body, null);
      var x = Object.assign({ id: nextId(db.sessions) }, pickKeys(body, F)); db.sessions.push(x); return [201, x]; }
    var item = byId(db.sessions, id, 'Регулярное занятие не найдено');
    if (method === 'PATCH') { noNull(body); only(body, F); checkSession(body, true);
      var next = Object.assign({}, item, body); if (next.start_time >= next.end_time) fail(422, 'Начало занятия должно быть раньше конца');
      if ('weekday' in body && body.weekday !== item.weekday) { var n = db.session_exceptions.filter(function (e) { return e.session_id === id; }).length; if (n) fail(409, 'Нельзя менять день недели: у занятия есть отмены/переносы (' + n + ') на прежний день. Сначала удалите их, затем меняйте день.'); }
      sessionConflict(next, id); Object.assign(item, body); return item; }
    if (method === 'DELETE') { db.session_exceptions = db.session_exceptions.filter(function (e) { return e.session_id !== id; }); db.sessions.splice(db.sessions.indexOf(item), 1); return [204, null]; }
  }
  function validateException(x) {
    var s = byId(db.sessions, x.session_id, 'Регулярное занятие не найдено');
    if (!DATE.test(x.original_date || '')) v422('Дата должна иметь формат YYYY-MM-DD');
    var wd = isoWeekday(parse(x.original_date));
    if (wd !== s.weekday) fail(422, 'original_date ' + x.original_date + ' — это ' + WD[wd - 1] + ', а занятие проходит по дням: ' + WD[s.weekday - 1]);
    if (x.type === 'moved') {
      if (!DATE.test(x.new_date || '')) v422('Дата должна иметь формат YYYY-MM-DD');
      if (isoWeekday(parse(x.new_date)) === 7) fail(422, 'Нельзя переносить занятие на воскресенье (в расписании нет воскресных занятий)');
      if (!CLOCK.test(x.new_start_time || '') || !CLOCK.test(x.new_end_time || '')) v422('Время в диапазоне 08:00–21:00 (ЧЧ:ММ)');
      if (x.new_start_time >= x.new_end_time) v422('Начало переноса должно быть раньше конца');
      byId(db.rooms, x.new_room_id, 'Аудитория не найдена');
    }
    if (typeof x.comment !== 'string' || x.comment.length > 4000) v422('comment: некорректное значение');
    if (db.session_exceptions.some(function (e) { return e.id !== x.id && e.session_id === x.session_id && e.original_date === x.original_date; }))
      fail(409, x.type === 'moved' ? 'Не удалось сохранить перенос занятия' : 'Не удалось сохранить отмену занятия');
  }
  function notify(e) {
    var s = db.sessions.find(function (q) { return q.id === e.session_id; }); var c = s && db.clubs.find(function (q) { return q.id === s.club_id; });
    db.notifications.unshift({ id: (db.notifications[0] ? db.notifications[0].id : 0) + 1, at: new Date().toISOString(), club_id: c ? c.id : null,
      title: (e.type === 'cancelled' ? 'Отмена: ' : 'Перенос: ') + (c ? c.name : 'занятие'), body: e.original_date + (e.type === 'moved' ? ' → ' + e.new_date + ' ' + e.new_start_time : '') + (e.comment ? ' — ' + e.comment : '') });
    db.notifications = db.notifications.slice(0, 50);
  }
  function crudExceptions(method, id, body, sub) {
    var EMPTY = { new_date: null, new_start_time: null, new_end_time: null, new_room_id: null };
    if (method === 'GET' && id == null) return db.session_exceptions.slice().sort(cmp('original_date', 'id'));
    if (method === 'POST' && (sub === 'cancellations' || sub === 'moves')) {
      var type = sub === 'moves' ? 'moved' : 'cancelled';
      var F = type === 'moved' ? ['session_id', 'original_date', 'type', 'new_date', 'new_start_time', 'new_end_time', 'new_room_id', 'comment'] : ['session_id', 'original_date', 'type', 'comment'];
      only(body, F); int(body, 'session_id', true);
      var x = Object.assign({ id: nextId(db.session_exceptions), comment: '' }, EMPTY, pickKeys(body, F.filter(function (k) { return k in body; })), { type: type });
      validateException(x); db.session_exceptions.push(x); notify(x); return [201, x];
    }
    var item = byId(db.session_exceptions, id, 'Изменение не найдено');
    if (method === 'PATCH') { noNull(body); if ('type' in body && body.type !== item.type) fail(422, 'Тип исключения нельзя менять');
      var next = Object.assign({}, item, body); validateException(next); Object.assign(item, next); notify(item); return item; }
    if (method === 'DELETE') { db.session_exceptions.splice(db.session_exceptions.indexOf(item), 1); return [204, null]; }
  }

  // ---------- анонимная посещаемость (как backend/app/routers/attendance.py + teacher.py; подпись в демо не секретная)
  // (B32 объявлен внутри randB32: seedAttendance вызывается из load() раньше, чем выполнится эта строка)
  function randB32(n, r) { var B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', s = ''; for (var i = 0; i < n; i++) s += B32[Math.floor((r ? r() : Math.random()) * 32)]; return s; }
  function grp(prefix, t) { return prefix + '-' + t.match(/.{1,4}/g).join('-'); }
  function normSid(raw) {
    var t = String(raw || '').replace(/[\s-]/g, '').toUpperCase(); if (t[0] === 'S') t = t.slice(1);
    if (!/^[A-Z2-7]{26}$/.test(t)) fail(422, 'ID студента выглядит так: S-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX');
    return grp('S', t);
  }
  function shortId(s) { return s.slice(0, 7) + '…' + s.slice(-2); }
  function windowMin() { return 15; }
  function freeWindow() { if (window.ITC_CHANNEL === 'p') return false; /* публичный канал: окно отметки как на сервере */ try { return localStorage.getItem('itc.demo.freeWindow') !== '0'; } catch (e) { return true; } }
  function seedAttendance() {
    var r = rng((Date.now() ^ 0xa77e) >>> 0);
    var pool = []; for (var k = 0; k < 60; k++) pool.push(grp('S', randB32(26, r)));
    var today = iso(new Date()), now = new Date(), hm = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
    for (var w = -3; w <= 0; w++) {
      buildWeek(addDays(monday(new Date()), w * 7)).forEach(function (e) {
        if (e.status === 'cancelled' || e.date > today || (e.date === today && e.start_time > hm)) return;
        if (parse(e.date) < addDays(new Date(), -21)) return; // хранение 21 день
        var n = 3 + Math.floor(r() * 12), seen = {};
        for (var i = 0; i < n; i++) {
          var sid = pool[Math.floor(r() * pool.length)]; if (seen[sid]) continue; seen[sid] = 1;
          var t = e.start_time.split(':'), at = parse(e.date); at.setHours(+t[0], +t[1] - 1 + Math.floor(r() * 14));
          db.attendance.push({ id: db.attendance.length + 1, session_id: e.session_id, date: e.original_date || e.date, student_id: sid, method: r() < 0.1 ? 'manual' : 'qr', at: at.toISOString() });
        }
      });
    }
  }
  function purgeAtt() { var cut = iso(addDays(new Date(), -21)); db.attendance = db.attendance.filter(function (x) { return x.date >= cut && x.student_id; }); }
  function occurrence(sessionId, day) {
    if (!DATE.test(day || '') || isNaN(parse(day))) fail(422, 'date должен иметь формат YYYY-MM-DD');
    if (!db.sessions.some(function (x) { return x.id === sessionId; })) fail(404, 'Занятие не найдено');
    var d = parse(day); var mon = new Date(d.getFullYear(), d.getMonth(), d.getDate() - isoWeekday(d) + 1);
    var e = buildWeek(mon).find(function (x) { return x.session_id === sessionId && x.date === day; });
    if (!e) { var c = db.session_exceptions.find(function (x) { return x.session_id === sessionId && x.original_date === day && x.type === 'cancelled'; });
      fail(c ? 409 : 404, c ? 'Это занятие отменено' : 'В этот день у кружка нет занятия'); }
    if (e.status === 'cancelled') fail(409, 'Это занятие отменено');
    return e;
  }
  function times(e) { var d = parse(e.date), a = e.start_time.split(':'), b = e.end_time.split(':');
    return [new Date(d.getFullYear(), d.getMonth(), d.getDate(), +a[0], +a[1]).getTime(), new Date(d.getFullYear(), d.getMonth(), d.getDate(), +b[0], +b[1]).getTime()]; }
  function qrPayload(sessionId, day) {
    var e = occurrence(sessionId, day), t = times(e), now = Date.now(), W = windowMin() * 60000;
    var base = { session_id: e.session_id, club_id: e.club_id, club_name: e.club_name, date: day, start_time: e.start_time, end_time: e.end_time,
      window_min: windowMin(), opens_at: new Date(t[0] - 10000).toISOString(), closes_at: new Date(t[0] + W).toISOString(), demo_free_window: freeWindow() };
    if (!freeWindow() && now < t[0] - 10000) return Object.assign(base, { state: 'early', opens_in: Math.ceil((t[0] - 10000 - now) / 1000) });
    if (!freeWindow() && now > t[0] + W) return Object.assign(base, { state: 'closed', manual_until: new Date(t[1]).toISOString() });
    var tok = 'itc-att2.' + btoa(JSON.stringify({ s: e.session_id, d: e.original_date || e.date, i: Math.floor(now / 1000), e: Math.floor(now / 1000) + 60 })).replace(/=+$/, '') + '.demo';
    return Object.assign(base, { state: 'open', token: tok, ttl: 60, rotate: 25, expires_at: new Date(now + 60000).toISOString(), closes_in: Math.max(0, Math.floor((t[0] + W - now) / 1000)) });
  }
  function record(sessionId, day, sid, method, enforce) {
    var e = occurrence(sessionId, day), t = times(e), now = Date.now();
    if (enforce === 'qr' && !freeWindow() && !(t[0] - 10000 <= now && now <= t[0] + windowMin() * 60000)) fail(403, now > t[0] ? 'Отметка закрыта' : 'Отметка ещё не открыта');
    if (enforce === 'session' && !freeWindow() && !(t[0] - 10000 <= now && now <= t[1])) fail(403, 'Ручная отметка доступна только во время занятия');
    var od = e.original_date || e.date;
    if (db.attendance.some(function (r) { return r.session_id === e.session_id && r.date === od && r.student_id === sid; })) fail(409, 'Уже отмечен(а) на занятии «' + e.club_name + '»');
    db.attendance.push({ id: nextId(db.attendance), session_id: e.session_id, date: od, student_id: sid, method: method, at: new Date().toISOString() });
    return [201, { ok: true, club_id: e.club_id, club_name: e.club_name, date: od, start_time: e.start_time, end_time: e.end_time, student_id: sid }];
  }
  function liveList(sessionId, day, since) {
    purgeAtt();
    var all = db.attendance.filter(function (r) { return r.session_id === sessionId && r.date === day; }).sort(cmp('at', 'id'));
    return { count: all.length, items: all.filter(function (r) { return r.id > (since || 0); }).map(function (r) { return { id: r.id, student_id: r.student_id, short: shortId(r.student_id), method: r.method, at: r.at }; }) };
  }
  function historyOf(sid) {
    purgeAtt();
    return { student_id: sid, retention_days: 21, items: db.attendance.filter(function (r) { return r.student_id === sid; }).map(function (r) {
      var ss = db.sessions.find(function (x) { return x.id === r.session_id; }) || {}; var c = db.clubs.find(function (x) { return x.id === ss.club_id; }) || { name: '?' };
      return { club_name: c.name, date: r.date, start_time: ss.start_time, end_time: ss.end_time, method: r.method, at: r.at }; }).sort(cmp(function (x) { return -parse(x.date).getTime(); }, 'start_time')) };
  }
  async function sha256hex(t) { var b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)); return Array.prototype.map.call(new Uint8Array(b), function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); }
  function hashSync(t) { var h = 0x811c9dc5; for (var i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return 'demo' + h.toString(16) + t.length; } // демо: не крипто
  function deviceCheck(sid, tok, register) {
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(tok || '')) fail(403, 'Нужен токен устройства');
    db.student_devices = db.student_devices || {}; var h = hashSync(tok), cur = db.student_devices[sid];
    if (!cur) { if (!register) fail(403, 'Это устройство не подтверждено: отметьтесь хотя бы раз на занятии'); db.student_devices[sid] = h; }
    else if (cur !== h) fail(403, 'ID привязан к другому устройству. Восстановите его резервным кодом.');
  }
  function checkin(body) {
    var sid = normSid(body.student_id), t = String(body.qr_token || ''), data;
    if (!/^[A-Za-z0-9_-]{16,64}$/.test(body.nonce || '')) fail(422, 'nonce');
    try { if (t.indexOf('itc-att2.') !== 0) throw 0; data = JSON.parse(atob(t.split('.')[1])); if (!data.s || !data.d || !data.e) throw 0; }
    catch (x) { fail(400, 'QR-код не распознан: это не код посещаемости ИТК'); }
    if (data.e * 1000 < Date.now()) fail(410, 'QR-код устарел — отсканируйте код на экране преподавателя ещё раз');
    if (data.s !== Number(body.session_id)) fail(409, 'Этот QR-код относится к другому занятию');
    db.nonces = (db.nonces || []).filter(function (n) { return n.e > Date.now(); });
    if (db.nonces.some(function (n) { return n.n === body.nonce; })) fail(409, 'Повторная отправка отклонена — отсканируйте QR ещё раз');
    deviceCheck(sid, body.device_token, true);
    db.nonces.push({ n: body.nonce, e: Date.now() + 300000 });
    return record(data.s, data.d, sid, 'qr', 'qr');
  }
  // преподаватели: в демо идентификатор T-… хранится открыто (на сервере — только SHA-256)
  function teacherByToken(tok) {
    var t = String(tok || '').replace(/[\s-]/g, '').toUpperCase(); if (t[0] === 'T') t = t.slice(1);
    var norm = /^[A-Z2-7]{26}$/.test(t) ? grp('T', t) : '';
    return db.leaders.find(function (l) { return l.access && l.access === norm; });
  }
  function issueAccess(l) { l.access = grp('T', randB32(26)); l.access_issued_at = new Date().toISOString();
    return { leader_id: l.id, name: l.name, token: l.access, issued_at: l.access_issued_at, note: 'Идентификатор показывается один раз — скопируйте и передайте преподавателю.' }; }
  function teacherFromReq(hdr) {
    var m = /^Bearer\s+tch-demo\.(\d+)\.(.+)$/.exec(hdr || ''); var l = m && db.leaders.find(function (x) { return x.id === +m[1]; });
    if (!l || !l.access || l.access_issued_at !== decodeURIComponent(m[2])) fail(401, 'Требуется вход преподавателя');
    return l;
  }
  function ownSession(l, sessionId) { var s = db.sessions.find(function (x) { return x.id === sessionId; }); var c = s && db.clubs.find(function (x) { return x.id === s.club_id; });
    if (!c || c.leader_id !== l.id) fail(403, 'Это занятие не относится к вашим кружкам'); return s; }
  function teacherRoute(method, p, q, body, auth) {
    if (p === '/api/teacher/login' && method === 'POST') { var l = teacherByToken(body.token); if (!l) fail(401, 'Неверный идентификатор преподавателя или доступ отозван');
      return { access_token: 'tch-demo.' + l.id + '.' + encodeURIComponent(l.access_issued_at), token_type: 'bearer', expires_in: 43200, teacher: { id: l.id, name: l.name } }; }
    if (p === '/api/teacher/transfer' && method === 'POST') { var tm = /^itc-tx1\.(\d+)\.([^.]+)\.(\d+)$/.exec(String(body.code || '').trim());
      var tx = tm && db.leaders.find(function (x) { return x.id === +tm[1]; });
      if (!tx || +tm[3] < Date.now() || encodeURIComponent(tx.access_issued_at || '-') !== tm[2]) fail(401, 'Код переноса недействителен или устарел — попросите администратора показать новый QR');
      var iss = issueAccess(tx); save();
      return { access_token: 'tch-demo.' + tx.id + '.' + encodeURIComponent(tx.access_issued_at), token_type: 'bearer', expires_in: 43200, teacher: { id: tx.id, name: tx.name }, token: iss.token }; }
    var t = teacherFromReq(auth);
    if (p === '/api/teacher/me') {
      var clubs = db.clubs.filter(function (c) { return c.leader_id === t.id && c.is_active; }).sort(cmp('name')); var ids = clubs.map(function (c) { return c.id; }); var rooms = idx(db.rooms);
      return { id: t.id, name: t.name, clubs: clubs.map(function (c) { return { id: c.id, name: c.name }; }),
        sessions: db.sessions.filter(function (s) { return ids.indexOf(s.club_id) >= 0; }).sort(cmp('weekday', 'start_time')).map(function (s) {
          return { id: s.id, club_id: s.club_id, club_name: (clubs.find(function (c) { return c.id === s.club_id; }) || {}).name, weekday: s.weekday, start_time: s.start_time, end_time: s.end_time, room_id: s.room_id, room_name: (rooms[s.room_id] || {}).name || '' }; }) };
    }
    if (p === '/api/teacher/attendance/qr' && method === 'POST') { ownSession(t, Number(body.session_id)); return qrPayload(Number(body.session_id), body.date); }
    if (p === '/api/teacher/attendance' && method === 'GET') { ownSession(t, Number(q.get('session_id'))); return liveList(Number(q.get('session_id')), q.get('date'), Number(q.get('since_id') || 0)); }
    if (p === '/api/teacher/attendance/manual' && method === 'POST') { ownSession(t, Number(body.session_id)); return record(Number(body.session_id), body.date, normSid(body.student_id), 'manual', 'session'); }
    var m = p.match(/^\/api\/teacher\/attendance\/(\d+)$/);
    if (m && method === 'DELETE') { var r = db.attendance.find(function (x) { return x.id === +m[1]; }); if (!r) fail(404, 'Отметка не найдена'); ownSession(t, r.session_id);
      db.attendance = db.attendance.filter(function (x) { return x !== r; }); console.info('[audit] attendance_revoked teacher:' + t.id + ' ' + shortId(r.student_id)); return [204, null]; }
    fail(404, 'Not Found');
  }
  function attendanceRoute(method, a, q, body) {
    if (a === '/attendance/qr' && method === 'POST') return qrPayload(Number(body.session_id), body.date);
    if (a === '/attendance/export.xlsx') return attendanceXlsx(q);
    if (a === '/attendance/manual' && method === 'POST') return record(Number(body.session_id), body.date, normSid(body.student_id), 'manual');
    if (a === '/attendance/student') return historyOf(normSid(q.get('student_id')));
    if (a === '/attendance/live') return liveList(Number(q.get('session_id')), q.get('date'), Number(q.get('since_id') || 0));
    var m = a.match(/^\/attendance\/(\d+)$/);
    if (m && method === 'DELETE') { db.attendance = db.attendance.filter(function (x) { return x.id !== +m[1]; }); return [204, null]; }
    if (a === '/attendance/stats') {
      purgeAtt();
      var to = q.get('date_to') || iso(new Date()); var from = q.get('date_from') || iso(new Date(parse(to).getTime() - 30 * 864e5));
      if (from > to) fail(422, 'date_from позже date_to');
      var cid = q.get('club_id') ? Number(q.get('club_id')) : null; var occ = {};
      db.attendance.forEach(function (r) {
        if (r.date < from || r.date > to) return;
        var ss = db.sessions.find(function (x) { return x.id === r.session_id; }); if (!ss || (cid && ss.club_id !== cid)) return;
        var club = db.clubs.find(function (x) { return x.id === ss.club_id; }) || { name: '?' };
        var k = r.session_id + '|' + r.date;
        (occ[k] = occ[k] || { session_id: r.session_id, date: r.date, count: 0, club_id: ss.club_id, club_name: club.name, start_time: ss.start_time }).count++;
      });
      var list = Object.keys(occ).map(function (k) { return occ[k]; }).sort(function (x, y) { return x.date < y.date ? 1 : x.date > y.date ? -1 : (x.start_time < y.start_time ? -1 : 1); });
      var clubs = {}; list.forEach(function (o) { var c = clubs[o.club_id] = clubs[o.club_id] || { club_id: o.club_id, club_name: o.club_name, classes: 0, checkins: 0 }; c.classes++; c.checkins += o.count; });
      var cl = Object.keys(clubs).map(function (k) { var c = clubs[k]; c.average = Math.round(c.checkins / c.classes * 10) / 10; return c; })
        .sort(function (x, y) { return y.checkins - x.checkins || (x.club_name < y.club_name ? -1 : 1); });
      return { date_from: from, date_to: to, total: list.reduce(function (n, o) { return n + o.count; }, 0), clubs: cl, occurrences: list };
    }
    if (a === '/attendance') return liveList(Number(q.get('session_id')), q.get('date')).items;
    if (a === '/teachers' && method === 'POST') { if (!body.name || String(body.name).trim().length < 2) fail(422, 'Укажите ФИО');
      var l = { id: nextId(db.leaders), name: String(body.name).trim().replace(/\s+/g, ' '), position: body.position || '', contact: '' }; db.leaders.push(l); return [201, issueAccess(l)]; }
    if (a === '/teachers') return db.leaders.slice().sort(cmp('name')).map(function (l) { return { leader_id: l.id, name: l.name, has_access: !!l.access, issued_at: l.access_issued_at || null }; });
    m = a.match(/^\/leaders\/(\d+)\/transfer$/);
    if (m && method === 'POST') { var tl = db.leaders.find(function (x) { return x.id === +m[1]; }); if (!tl) fail(404, 'Руководитель не найден');
      return { leader_id: tl.id, name: tl.name, code: 'itc-tx1.' + tl.id + '.' + encodeURIComponent(tl.access_issued_at || '-') + '.' + (Date.now() + 600000), expires_in: 600 }; }
    m = a.match(/^\/leaders\/(\d+)\/access$/);
    if (m) { var ld = db.leaders.find(function (x) { return x.id === +m[1]; }); if (!ld) fail(404, 'Руководитель не найден');
      if (method === 'POST') return issueAccess(ld); if (method === 'DELETE') { ld.access = null; ld.access_issued_at = null; return [204, null]; } }
    return null;
  }
  function attendanceXlsx(q) {
    var s = attendanceRoute('GET', '/attendance/stats', q, {});
    var sheets = [{ name: 'Сводка', rows: [['Посещаемость кружков: ' + s.date_from + ' — ' + s.date_to], [], ['Кружок', 'Занятий с отметками', 'Отметок', 'В среднем на занятии']]
      .concat(s.clubs.map(function (c) { return [c.club_name, c.classes, c.checkins, c.average]; }))
      .concat([['Итого', s.clubs.reduce(function (n, c) { return n + c.classes; }, 0), s.total, null]]), widths: [44, 22, 12, 22], bold: [0, 2, 3 + s.clubs.length], freeze: 3 }];
    s.clubs.forEach(function (c) {
      var club = db.clubs.find(function (x) { return x.id === c.club_id; }) || {}; var teacher = (db.leaders.find(function (l) { return l.id === club.leader_id; }) || {}).name || '';
      var rows = db.attendance.filter(function (a) { var ss = db.sessions.find(function (x) { return x.id === a.session_id; }); return ss && ss.club_id === c.club_id && a.date >= s.date_from && a.date <= s.date_to; })
        .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : (a.at < b.at ? -1 : 1); })
        .map(function (a) { var ss = db.sessions.find(function (x) { return x.id === a.session_id; }); var t = new Date(a.at);
          return [parse(a.date), ss.start_time + '–' + ss.end_time, teacher, a.student_id, String(t.getHours()).padStart(2, '0') + ':' + String(t.getMinutes()).padStart(2, '0')]; });
      sheets.push({ name: c.club_name, rows: [['Дата', 'Время', 'Преподаватель', 'ID студента', 'Отметился в']].concat(rows), widths: [12, 14, 30, 40, 14], bold: [0], freeze: 1 });
    });
    return { __file: window.ItcXlsx.build(sheets), name: 'attendance_' + s.date_from + '_' + s.date_to + '.xlsx', type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' };
  }

  // ---------- маршрутизатор
  function route(method, url, body) {
    var u = new URL(url, location.origin); var p = u.pathname.replace(/\/+$/, ''); var q = u.searchParams; var m;
    var qi = function (k) { var v = q.get(k); return v == null || v === '' ? null : Number(v); };
    if (p === '/api/health') return { status: 'ok', mode: 'demo' };
    if (p === '/api/categories') return db.categories.slice().sort(cmp('name', 'id'));
    if (p === '/api/leaders') { var act = db.clubs.filter(function (c) { return c.is_active; }).map(function (c) { return c.leader_id; });
      return db.leaders.filter(function (l) { return act.indexOf(l.id) >= 0; }).sort(cmp('name', 'id')).map(function (l) { return pickKeys(l, ['id', 'name', 'position']); }); }
    if (p === '/api/rooms') return db.rooms.slice().sort(cmp('building', 'name', 'id'));
    if (p === '/api/clubs') {
      var items = db.clubs.filter(function (c) { return c.is_active && (qi('category_id') == null || c.category_id === qi('category_id')); }).sort(cmp('name', 'id'));
      var s = (q.get('search') || '').trim().toLowerCase();
      return s ? items.filter(function (c) { return c.name.toLowerCase().indexOf(s) >= 0 || c.description.toLowerCase().indexOf(s) >= 0; }) : items;
    }
    if ((m = p.match(/^\/api\/clubs\/(\d+)\/calendar\.ics$/))) return { __ics: +m[1], week: q.get('week') };
    if ((m = p.match(/^\/api\/clubs\/(\d+)$/))) {
      var c = db.clubs.find(function (x) { return x.id === +m[1] && x.is_active; }); if (!c) fail(404, 'Кружок не найден');
      var rooms = idx(db.rooms);
      var ss = db.sessions.filter(function (x) { return x.club_id === c.id; }).sort(cmp('weekday', 'start_time', 'id'));
      var sid = ss.map(function (x) { return x.id; });
      return Object.assign({}, c, { category: idx(db.categories)[c.category_id], leader: idx(db.leaders)[c.leader_id],
        sessions: ss.map(function (x) { return Object.assign({}, x, { room: rooms[x.room_id] }); }),
        upcoming_exceptions: db.session_exceptions.filter(function (e) { return sid.indexOf(e.session_id) >= 0; }).sort(cmp('original_date', function (e) { return e.new_date || e.original_date; }, function (e) { return e.new_start_time || ''; }, 'id')) });
    }
    if (p === '/api/schedule') {
      var week = q.get('week') || '';
      if (!DATE.test(week) || isNaN(parse(week))) fail(422, 'week должен иметь формат YYYY-MM-DD');
      if (isoWeekday(parse(week)) !== 1) fail(422, 'week должен указывать на понедельник выбранной недели');
      var ev = buildWeek(parse(week)); var f;
      if ((f = qi('category_id')) != null) ev = ev.filter(function (e) { return e.category_id === f; });
      if ((f = qi('weekday')) != null) ev = ev.filter(function (e) { return isoWeekday(parse(e.date)) === f; });
      if ((f = qi('leader_id')) != null) ev = ev.filter(function (e) { return e.leader_id === f; });
      if ((f = qi('room_id')) != null) ev = ev.filter(function (e) { return e.room_id === f; });
      var n = (q.get('search') || '').trim().toLowerCase();
      if (n) ev = ev.filter(function (e) { return [e.club_name, e.category_name, e.leader_name, e.room_name].some(function (t) { return t.toLowerCase().indexOf(n) >= 0; }); });
      return ev;
    }
    // push — заглушка (нативный FCM не подключён; подписки хранятся локально)
    if (p === '/api/push/vapid-public-key') return { publicKey: 'BDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDemoKeyDem' };
    if (p === '/api/push/status') { var ep = body && body.endpoint; var mine = db.push_subscriptions.filter(function (x) { return x.endpoint === ep; });
      return { all: mine.some(function (x) { return x.club_id == null; }), club_ids: mine.map(function (x) { return x.club_id; }).filter(Boolean) }; }
    if (p === '/api/push/subscribe') { db.push_subscriptions.push({ endpoint: body.endpoint, club_id: body.club_id || null }); return [201, { status: 'subscribed' }]; }
    if (p === '/api/push/unsubscribe') { db.push_subscriptions = db.push_subscriptions.filter(function (x) { return !(x.endpoint === body.endpoint && (body.club_id == null || x.club_id === body.club_id)); }); return [204, null]; }
    if (p === '/api/attendance/checkin' && method === 'POST') return checkin(body || {});
    if (p === '/api/attendance/mine') { var hs = curHdr; var msid = normSid(hs['x-student-id']); deviceCheck(msid, hs['x-device-token'], false); return historyOf(msid); }
    if (p.indexOf('/api/teacher/') === 0) return teacherRoute(method, p, q, body || {}, curHdr.authorization);
    // админка: вход всегда выполнен (демо)
    if (p.indexOf('/api/admin') === 0) {
      var a = p.slice('/api/admin'.length);
      var TOKENS = { status: 'authenticated', access_token: 'demo-access', refresh_token: 'demo-refresh-token', token_type: 'bearer', expires_in: 900, refresh_expires_in: 2592000 };
      if (a === '/login') {
        // настоящая проверка логина/пароля по демо-учёткам; успешный вход снимает флаг «вышел явно»
        var cred = db.admins.find(function (x) { return body && x.login === String(body.login || '').trim() && x.password === body.password; });
        if (!cred) fail(401, 'Неверный логин или пароль');
        setLoggedOut(false); return Object.assign({ admin: { id: cred.id, login: cred.login } }, TOKENS);
      }
      if (a === '/logout') { setLoggedOut(true); return [204, null]; }
      if (loggedOut()) fail(401, 'Требуется вход');
      if (a === '/refresh') return Object.assign({ admin: ADMIN }, TOKENS);
      if (a === '/status') return { admin: ADMIN, status: 'authenticated' };
      if (a === '/password') { var ad = db.admins[0]; if (body.current_password !== ad.password) fail(403, 'Текущий пароль указан неверно');
        if (!body.new_password || body.new_password.length < 8) fail(422, 'Пароль должен быть не короче 8 символов'); if (body.new_password === ad.password) fail(422, 'Новый пароль должен отличаться от текущего'); ad.password = body.new_password; return [204, null]; }
      if (a === '/notifications') return db.notifications;
      if (a === '/users') return db.users;
      if (a.indexOf('/attendance') === 0 || a.indexOf('/teachers') === 0 || /^\/leaders\/\d+\/(access|transfer)$/.test(a)) { var ar = attendanceRoute(method, a, q, body || {}); if (ar) return ar; }
      m = a.match(/^\/(categories|leaders|rooms|clubs|sessions|exceptions)(?:\/(\d+|cancellations|moves))?$/);
      if (m) {
        var id = m[2] && /^\d+$/.test(m[2]) ? +m[2] : null; var sub = id == null ? m[2] : null;
        if (method === 'GET' && id != null) fail(405, 'Method Not Allowed');
        if (method === 'POST' && id != null) fail(405, 'Method Not Allowed');
        if ((method === 'PATCH' || method === 'DELETE') && id == null) fail(405, 'Method Not Allowed');
        var fn = { categories: crudCategories, leaders: crudLeaders, rooms: crudRooms, clubs: crudClubs, sessions: crudSessions, exceptions: crudExceptions }[m[1]];
        if (method === 'POST' && m[1] !== 'exceptions' && sub) fail(404, 'Not Found');
        if (method === 'POST' && m[1] === 'exceptions' && !sub) fail(405, 'Method Not Allowed');
        return fn(method, id, body || {}, sub);
      }
    }
    fail(404, 'Not Found');
  }

  function ics(clubId, week) {
    var c = db.clubs.find(function (x) { return x.id === clubId; }); if (!c) fail(404, 'Кружок не найден');
    var start = week && DATE.test(week) ? parse(week) : monday(new Date());
    var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ITC Kruzhki demo//RU'];
    buildWeek(start).filter(function (e) { return e.club_id === clubId && e.status !== 'cancelled'; }).forEach(function (e) {
      var d = e.date.replace(/-/g, ''); lines.push('BEGIN:VEVENT', 'UID:' + e.event_id + '@itc-demo', 'DTSTART:' + d + 'T' + e.start_time.replace(':', '') + '00', 'DTEND:' + d + 'T' + e.end_time.replace(':', '') + '00', 'SUMMARY:' + e.club_name, 'LOCATION:' + e.room_name, 'END:VEVENT');
    });
    lines.push('END:VCALENDAR'); return lines.join('\r\n');
  }

  function respond(status, data, type) {
    var hdr = { 'Content-Type': type || 'application/json', 'X-Demo-Backend': '1' };
    if (status === 204) return new Response(null, { status: 204, headers: hdr });
    return new Response(type ? data : JSON.stringify(data), { status: status, headers: hdr });
  }
  var curHdr = {};
  function handle(method, url, rawBody, hdrs) {
    var body = null; curHdr = hdrs || {};
    if (rawBody != null && rawBody !== '') { try { body = JSON.parse(rawBody); } catch (e) { return respond(422, { detail: [{ msg: 'Некорректный JSON' }] }); } }
    var snapshot = JSON.stringify(db);
    try {
      var out = route(method, url, body);
      if (out && out.__ics) return respond(200, ics(out.__ics, out.week), 'text/calendar');
      if (out && out.__file) { var fr = respond(200, out.__file, out.type); fr.headers.set('Content-Disposition', 'attachment; filename*=UTF-8\'\'' + encodeURIComponent(out.name)); return fr; }
      var status = 200, data = out; if (Array.isArray(out) && out.length === 2 && typeof out[0] === 'number') { status = out[0]; data = out[1]; }
      if (method !== 'GET') save();
      return respond(status, JSON.parse(JSON.stringify(data)));
    } catch (e) {
      db = JSON.parse(snapshot); // откат «транзакции»
      if (e instanceof Http) return respond(e.status, { detail: e.detail });
      console.error('[demo-backend]', e); return respond(500, { detail: 'Внутренняя ошибка демо-бэкенда: ' + e.message });
    }
  }

  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var path; try { var u = new URL(url, location.href); path = u.origin === location.origin ? u.pathname + u.search : null; } catch (e) { path = null; }
    if (path && path.indexOf('/api/') === 0) {
      var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      var raw = init && init.body != null ? String(init.body) : null;
      var hdrs = {}; try { new Headers((init && init.headers) || (input && input.headers) || {}).forEach(function (v, k) { hdrs[k.toLowerCase()] = v; }); } catch (e) { /* без заголовков */ }
      return new Promise(function (resolve, reject) {
        var signal = init && init.signal; if (signal && signal.aborted) return reject(new DOMException('Запрос отменён', 'AbortError'));
        setTimeout(function () { if (signal && signal.aborted) return reject(new DOMException('Запрос отменён', 'AbortError')); resolve(handle(method, path, raw, hdrs)); }, 40);
      });
    }
    return origFetch.apply(window, arguments);
  };
  // ссылка «в календарь» (.ics): отдаём файл, сгенерированный локально
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href^="/api/"]'); if (!a) return;
    e.preventDefault();
    window.fetch(a.getAttribute('href')).then(function (r) { return r.blob(); }).then(function (b) {
      var l = document.createElement('a'); l.href = URL.createObjectURL(b); l.download = 'club.ics'; document.body.appendChild(l); l.click(); l.remove();
    });
  }, true);
  // вход не нужен: страница логина сразу ведёт в админку (кроме случая, когда пользователь вышел явно — тогда обычный экран входа)
  if (/^\/admin\/login(\.html)?$/.test(location.pathname) && !loggedOut()) {
    var next = new URLSearchParams(location.search).get('next') || '';
    location.replace('/admin/index.html' + (/^#\/[\w\-/]*$/.test(next) ? next : ''));
  }

  window.DemoBackend = {
    enabled: true,
    reset: function () { db = seed(); db.seed2 = 1; db.attendance = []; seedAttendance(); db.attSeeded = 2; save(); },
    loggedOut: loggedOut,
    stats: function () { return { clubs: db.clubs.length, leaders: db.leaders.length, rooms: db.rooms.length, sessions: db.sessions.length, exceptions: db.session_exceptions.length, users: db.users.length, seededAt: db.seededAt }; },
    notifications: function () { return db.notifications.slice(); },
    _db: function () { return db; }
  };
})();
