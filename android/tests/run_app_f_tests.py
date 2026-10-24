"""Phase 2 F: новый экран «Расписание» APK, меню ⋮, свайп дней, кэш, параллельные занятия, экран загрузки, обновления,
админка. Chromium + мок Capacitor (как WebView), демо-сборка www (APP_DEMO=1 prepare-web). Без эмулятора.
Скриншоты (светлая/тёмная) -> SHOTS_DIR."""
import os, sys, json, threading, http.server, functools, socketserver, re
from pathlib import Path
from playwright.sync_api import sync_playwright

WWW = Path(os.environ.get("WWW", Path(__file__).resolve().parent.parent / "www"))
SHOTS = Path(os.environ.get("SHOTS_DIR", "/workspace/itc/shots_f")); SHOTS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("STATIC_PORT", "9141"))
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail else ""), flush=True)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(WWW))); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"
MOCK = """
window.__calls = [];
const rec = (n, ret) => (a) => { window.__calls.push([n, JSON.parse(JSON.stringify(a || {}))]); return Promise.resolve(typeof ret === 'function' ? ret(a) : (ret || {})); };
const upd = JSON.parse(localStorage.getItem('__qa.update') || 'null');
window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android', Plugins: {
  ItcNative: new Proxy({}, { get: (t, k) => rec(String(k), { notificationsAllowed: true, requested: true }) }),
  ItcUpdate: { splashReady: rec('splashReady'), appInfo: rec('appInfo', { versionCode: 3, versionName: '1.2', canInstall: true }),
    check: rec('check', () => upd ? { status: 200, body: JSON.stringify(upd) } : { status: 404, body: '' }),
    download: (a) => { window.__calls.push(['download', a]); const l = window.__prog; if (l) { l({ loaded: 50, total: 100 }); l({ loaded: 100, total: 100 }); }
      return new Promise(r => setTimeout(() => r({ path: '/x/update.apk', sha256: a.sha256 }), 200)); },
    install: rec('install', { started: true }), openExternal: rec('openExternal'),
    addListener: (ev, fn) => { window.__prog = fn; return Promise.resolve({ remove() {} }); } },
  App: { addListener: () => ({ remove() {} }), getLaunchUrl: () => Promise.resolve({}) } } };
"""
def calls(pg, n): return [a for k, a in pg.evaluate("window.__calls") if k == n]
def swipe(pg, x0, x1, y0=560, y1=None, steps=8):
    y1 = y0 if y1 is None else y1
    cdp = pg.context.new_cdp_session(pg)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / steps, "y": y0 + (y1 - y0) * i / steps}]})
        pg.wait_for_timeout(16)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    pg.wait_for_timeout(450)
def sel_day(pg): return pg.evaluate("[...document.querySelectorAll('#day-buttons > button')].findIndex(b => b.getAttribute('aria-pressed')==='true')")
def wk(pg): return pg.evaluate("document.getElementById('app-range').textContent")
def ready(pg): pg.wait_for_function("window.ItcPerf && window.ItcPerf.firstContent && !document.documentElement.classList.contains('itc-splash-on')", timeout=15000)

with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    def ctx(scheme="light", w=390, h=844):
        c = br.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True, color_scheme=scheme, device_scale_factor=2,
                           user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36")
        c.add_init_script(MOCK); return c
    for scheme in ("light", "dark"):
        c = ctx(scheme); pg = c.new_page(); errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        sfx = "-" + scheme
        # --- экран загрузки (холодный старт)
        pg.goto(B + "/index.html"); pg.wait_for_timeout(250)
        vis = pg.evaluate("(() => { const s = document.getElementById('itc-splash'); return !!s && getComputedStyle(s).display !== 'none'; })()")
        check("сплэш виден при холодном старте" + sfx, vis)
        foot = pg.text_content("#itc-splash .itc-splash-foot") if vis else ""
        check("сплэш: версия и «Продукт ИТС КИПФИН»" + sfx, "Версия" in foot and "Продукт ИТС КИПФИН" in foot, foot)
        pg.screenshot(path=str(SHOTS / f"splash{sfx}.png"))
        ready(pg)
        el = pg.evaluate("performance.now()")
        check("сплэш не меньше 600 мс" + sfx, el >= 600, f"{el:.0f}")
        check("системный сплэш отпущен (splashReady)" + sfx, len(calls(pg, "splashReady")) >= 1)
        pg.wait_for_timeout(400)
        # --- раскладка
        check("нет заголовка «Расписание» и полосы недель" + sfx, pg.locator("main h1").count() == 0 and pg.locator("#prev-week, #next-week, .week-toolbar").count() == 0)
        check("в шапке одна ссылка «Все кружки»" + sfx, pg.evaluate("[...document.querySelectorAll('.campus-header nav a')].map(a=>a.textContent)") == ["Все кружки"])
        check("нет «Вход для сотрудников» в шапке" + sfx, pg.locator(".campus-header .staff-link").count() == 0)
        sr = pg.locator(".app-search-row").bounding_box(); db_ = pg.locator("#app-date").bounding_box()
        check("поиск во всю ширину + кнопка даты справа" + sfx, sr and db_ and sr["width"] > 330 and db_["x"] > 300 and db_["width"] <= 48)
        check("«Сегодня» вместо «Текущая неделя»" + sfx, pg.text_content("#today").strip() == "Сегодня")
        check("фильтры — кнопка-иконка" + sfx, pg.locator("#toggle-filters").bounding_box()["width"] <= 48)
        rng = wk(pg)
        check("диапазон недели «19–24 октября»" + sfx, re.fullmatch(r"\d{1,2}(–\d{1,2} [а-я]+| [а-я]+ – \d{1,2} [а-я]+)( \d{4})?", rng) is not None, rng)
        check("нет «За день: N · отменено»" + sfx, "За день" not in pg.inner_text("main"))
        hdr = pg.evaluate("getComputedStyle(document.querySelector('.campus-header')).borderBottomWidth")
        check("нет разделителя под шапкой" + sfx, hdr in ("0px",), hdr)
        pg.screenshot(path=str(SHOTS / f"schedule{sfx}.png"))
        # полоса дней прилипает
        pg.evaluate("document.getElementById('content').style.minHeight='3000px'; window.scrollTo(0, 600)"); pg.wait_for_timeout(200)
        top = pg.locator("#app-days").bounding_box()["y"]
        check("полоса дней прилипает сверху" + sfx, -1 <= top <= 40, f"{top:.0f}")
        pg.evaluate("window.scrollTo(0, 0); document.getElementById('content').style.minHeight=''")
        # --- меню ⋮
        pg.click("#app-menu-btn"); pg.wait_for_timeout(250)
        items = pg.inner_text("#app-menu")
        check("меню: тема, Настройки, Вход для сотрудников" + sfx, all(x in items for x in ("Системная", "Светлая", "Тёмная", "Настройки", "Вход для сотрудников")), items.replace("\n", " | "))
        pg.screenshot(path=str(SHOTS / f"menu{sfx}.png"))
        other = "dark" if scheme == "light" else "light"
        pg.click(f'#app-menu [data-theme-set="{other}"]'); pg.wait_for_timeout(300)
        check("меню: переключение темы" + sfx, pg.get_attribute("html", "data-theme") == other)
        pg.click('#app-menu [data-theme-set="system"]'); pg.wait_for_timeout(200)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
        check("меню закрывается по Esc" + sfx, pg.locator("#app-menu").count() == 0)
        pg.click("#app-menu-btn"); pg.click('#app-menu [data-act="settings"]'); pg.wait_for_timeout(400)
        check("«Настройки» открывают окно настроек" + sfx, pg.locator("dialog[open]").count() >= 1)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        # --- свайп
        pg.evaluate("ItcSchedule.goto('2026-10-21')"); pg.wait_for_timeout(500)
        d0, w0 = sel_day(pg), wk(pg)
        swipe(pg, 320, 90)
        check("свайп влево → следующий день" + sfx, sel_day(pg) == d0 + 1, f"{d0}->{sel_day(pg)}")
        swipe(pg, 90, 320)
        check("свайп вправо → предыдущий день" + sfx, sel_day(pg) == d0)
        swipe(pg, 6, 260)
        check("свайп от края (жест «Назад») не листает" + sfx, sel_day(pg) == d0)
        swipe(pg, 200, 240, 600, 300)
        check("вертикальная прокрутка не листает" + sfx, sel_day(pg) == d0)
        pg.evaluate("ItcSchedule.goto('2026-10-24')"); pg.wait_for_timeout(500)
        swipe(pg, 320, 90); pg.wait_for_timeout(400)
        check("свайп через границу недели (Сб → Пн)" + sfx, sel_day(pg) == 0 and wk(pg) != w0, wk(pg))
        swipe(pg, 90, 320); pg.wait_for_timeout(300)
        check("обратно через неделю (Пн → Сб)" + sfx, sel_day(pg) == 5 and wk(pg) == w0)
        # «Сегодня»
        pg.click("#today"); pg.wait_for_timeout(500)
        check("«Сегодня» нажата и подсвечена" + sfx, pg.get_attribute("#today", "aria-pressed") == "true")
        # --- параллельные занятия: ищем день с одинаковым началом
        par = pg.evaluate("""(async () => { for (let w = 0; w < 6; w++) { const m = new Date(Date.now()+3*3600e3); m.setUTCDate(m.getUTCDate()-((m.getUTCDay()+6)%7)+7*w);
           const r = await (await fetch('/api/schedule?week=' + m.toISOString().slice(0,10))).json(); const seen = {};
           for (const e of r) { if (e.status === 'cancelled') continue; const k = e.date + e.start_time; if (seen[k]) return e.date; seen[k] = 1; } } return null; })()""")
        if par:
            pg.evaluate(f"ItcSchedule.goto('{par}')"); pg.wait_for_timeout(700)
            check("параллельные занятия — в одном слоте" + sfx, pg.locator(".app-slot .calendar-event").count() >= 2)
            pg.locator(".app-slot").first.scroll_into_view_if_needed(); pg.wait_for_timeout(200)
            pg.screenshot(path=str(SHOTS / f"parallel{sfx}.png"))
            pg.locator(".app-slot .calendar-event").first.click(); pg.wait_for_timeout(300)
            check("в подробностях — «Параллельно»" + sfx, "Параллельно" in pg.inner_text("#event-details"))
            pg.click("#close-event")
        else: check("есть день с параллельными занятиями (демо)" + sfx, False)
        # --- кэш: повторная загрузка — без скелетона, сразу из кэша
        pg.evaluate("sessionStorage.setItem('itc.booted','1')")
        pg.goto(B + "/index.html"); pg.wait_for_function("window.ItcPerf && window.ItcPerf.firstContent")
        ttfc = pg.evaluate("window.ItcPerf.firstContent")
        check("тёплый старт: контент из кэша без экрана загрузки" + sfx, pg.locator("#itc-splash").evaluate("e => getComputedStyle(e).display") == "none" and ttfc < 1500, f"{ttfc:.0f} мс")
        # --- каталог: переключатель «Расписание»
        pg.goto(B + "/clubs.html"); pg.wait_for_timeout(600)
        check("каталог: в шапке «Расписание»" + sfx, pg.evaluate("[...document.querySelectorAll('.campus-header nav a')].map(a=>a.textContent)") == ["Расписание"])
        # --- обновление
        pg.evaluate("""localStorage.setItem('__qa.update', JSON.stringify({ versionCode: 4, versionName: '1.3', size: 5242880, sha256: 'ab'.repeat(32),
            url: '/android/download', changelog: ['Новое расписание: свайпы, «Сегодня», быстрая загрузка', 'Экран загрузки', 'Обновления внутри приложения'], minSupported: 1 }));
            localStorage.setItem('itc.updateUrl', 'https://example.test/api/app/android')""")
        pg.goto(B + "/index.html"); ready(pg) if False else pg.wait_for_function("window.ItcAppUpdate")
        pg.evaluate("ItcAppUpdate.check({ manual: true })"); pg.wait_for_selector("#app-update-sheet", timeout=4000)
        check("шторка «Доступно обновление 1.3»" + sfx, "Доступно обновление 1.3" in pg.inner_text("#app-update-sheet"))
        check("есть «Позже» (не обязательное)" + sfx, pg.locator("#app-update-sheet [data-later]").count() == 1)
        pg.screenshot(path=str(SHOTS / f"update{sfx}.png"))
        pg.click("#app-update-sheet .btn--filled"); pg.wait_for_timeout(700)
        dl = calls(pg, "download")
        check("скачивание с sha256 и абсолютным URL" + sfx, dl and dl[-1]["sha256"] == "ab" * 32 and dl[-1]["url"] == "https://example.test/android/download", str(dl[-1] if dl else ""))
        check("после скачивания — установщик" + sfx, len(calls(pg, "install")) == 1)
        pg.evaluate("""localStorage.setItem('__qa.update', JSON.stringify({ versionCode: 9, versionName: '2.0', minSupported: 5, url: '/android/download' }))""")
        pg.goto(B + "/index.html"); pg.wait_for_function("window.ItcAppUpdate")
        pg.evaluate("ItcAppUpdate.check({ manual: true })"); pg.wait_for_selector("#app-update-sheet", timeout=4000)
        check("обязательное обновление — без «Позже»" + sfx, pg.locator("#app-update-sheet [data-later]").count() == 0)
        pg.evaluate("localStorage.removeItem('__qa.update')")
        pg.goto(B + "/index.html"); pg.wait_for_function("window.ItcAppUpdate")
        r = pg.evaluate("ItcAppUpdate.check({}).then(x => x)")
        check("сервер недоступен — тихо, без шторки" + sfx, r is None and pg.locator("#app-update-sheet").count() == 0)
        pg.evaluate("localStorage.removeItem('itc.updateUrl')")
        # --- админка
        pg.goto(B + "/admin/index.html#/clubs"); pg.wait_for_selector(".app-admin-hint", timeout=8000); pg.wait_for_timeout(500)
        h1 = pg.locator(".admin-head h1").first.bounding_box()
        check("админка: заголовок раздела скрыт визуально" + sfx, h1 is None or h1["height"] <= 1)
        check("админка: подсказка «Кружок — это карточка»" + sfx, "карточка" in pg.text_content(".app-admin-hint"))
        check("админка: вкладка «Расписание» вместо «Занятия»" + sfx, "Расписание" in pg.inner_text(".bottom-nav") and "Занятия" not in pg.inner_text(".bottom-nav"))
        pg.screenshot(path=str(SHOTS / f"admin-clubs{sfx}.png"))
        link = pg.locator("a.app-xlink").first; name = pg.locator("td[data-label='Название'] strong").first.text_content()
        link.click(); pg.wait_for_timeout(900)
        sel = pg.evaluate("(() => { const s = document.querySelector('select[aria-label=\"Кружок\"]'); return s && s.options[s.selectedIndex].textContent; })()")
        check("кружок → его расписание (фильтр применён)" + sfx, sel == name, f"{sel} / {name}")
        pg.locator("td[data-label='Кружок'] a.app-xlink").first.click(); pg.wait_for_timeout(900)
        q = pg.evaluate("document.querySelector('#admin-main input[type=search]')?.value")
        check("занятие → карточка кружка" + sfx, q == name, str(q))
        pg.goto(B + "/admin/index.html#/sessions"); pg.wait_for_selector("td[data-label='Время']", timeout=8000); pg.wait_for_timeout(500)
        check("админка: метки «параллельно»" + sfx, pg.locator(".app-par").count() >= 1 if par else True)
        pg.screenshot(path=str(SHOTS / f"admin-sessions{sfx}.png"))
        check("без ошибок JS" + sfx, not errors, "; ".join(errors[:3]))
        c.close()
    # глубокая ссылка ?my=1, офлайн, двойные нажатия
    c = ctx("light"); pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/index.html"); pg.evaluate("sessionStorage.setItem('itc.booted','1'); localStorage.setItem('itc.follows', JSON.stringify([1,2,3]))")
    pg.goto(B + "/index.html?my=1"); pg.wait_for_function("window.ItcPerf && window.ItcPerf.firstContent"); pg.wait_for_timeout(900)
    names = pg.evaluate("[...document.querySelectorAll('#content .event-name')].map(e=>e.textContent.trim())")
    allowed = pg.evaluate("DemoBackend._db().clubs.filter(c=>[1,2,3].includes(c.id)).map(c=>c.name)")
    check("?my=1: только «Мои кружки»", all(n in allowed for n in names) and pg.get_attribute("#itc-my-toggle", "aria-pressed") == "true", str(names))
    pg.evaluate("localStorage.setItem('itc.myMode','0')")
    pg.goto(B + "/index.html"); pg.wait_for_function("window.ItcPerf && window.ItcPerf.firstContent"); pg.wait_for_timeout(500)
    before = pg.evaluate("document.querySelectorAll('#content .calendar-event').length")
    for _ in range(6): pg.locator("#day-buttons > button").nth(2).click(); pg.locator("#day-buttons > button").nth(3).click()
    pg.wait_for_timeout(900)
    ok = pg.evaluate("""(async () => { const st = ItcSchedule.state; const wk = new Date(st.week.getTime() - st.week.getTimezoneOffset()*6e4).toISOString().slice(0,10);
        const r = await (await fetch('/api/schedule?week=' + wk)).json(); const d = new Date(st.week); d.setDate(d.getDate() + st.day);
        const dk = new Date(d.getTime() - d.getTimezoneOffset()*6e4).toISOString().slice(0,10);
        return st.day === 3 && document.querySelectorAll('#content .calendar-event').length === r.filter(e => e.date === dk).length; })()""")
    check("быстрые нажатия по дням: показан последний выбранный день", ok)
    check("без ошибок JS (ссылки/офлайн)", not errs, "; ".join(errs[:3]))
    c.close()
    # 360 px и крупный шрифт: ничего не вылезает по горизонтали
    for w, scale in ((360, 1), (360, 2)):
        c = ctx("light", w, 780); pg = c.new_page()
        pg.goto(B + "/index.html"); pg.evaluate("sessionStorage.setItem('itc.booted','1')")
        if scale > 1: pg.evaluate("localStorage.setItem('clubs.prefs', JSON.stringify({theme:'light',accent:'brick',textSize:'xlarge'}))")
        pg.goto(B + "/index.html"); pg.wait_for_function("window.ItcPerf && window.ItcPerf.firstContent"); pg.wait_for_timeout(500)
        ov = pg.evaluate("""[...document.querySelectorAll('.campus-header *, #schedule-filters *, #app-days *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.right > innerWidth + 1 || r.left < -1); }).map(e => e.id || e.className).slice(0,5)""")
        check(f"{w}px x{scale}: ничего не выходит за экран", not ov, str(ov))
        pg.screenshot(path=str(SHOTS / f"schedule-{w}-x{scale}.png"))
        c.close()
    br.close()
bad = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} PASS"); sys.exit(1 if bad else 0)
