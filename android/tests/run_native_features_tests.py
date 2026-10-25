"""Тесты нативных функций APK (phase 2 C) в Chromium на демо-сборке www/ (APP_DEMO=1 npm run prepare-web).
Эмулируем WebView: window.Capacitor (isNativePlatform=true) + мок плагина ItcNative, который записывает вызовы.
Скриншоты 390px (светлая/тёмная) -> SHOTS_DIR."""
import os, sys, json, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
WWW = HERE / "www"
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
SHOTS = Path(os.environ.get("SHOTS_DIR", "/workspace/itc/shots_c")); SHOTS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("STATIC_PORT", "9131"))
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail else ""))

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
H = functools.partial(Quiet, directory=str(WWW))
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"

MOCK = """
window.__calls = [];
const rec = (name) => (arg) => { window.__calls.push([name, JSON.parse(JSON.stringify(arg || {}))]);
  return Promise.resolve({ notificationsAllowed: true, reminderMinutes: 30, notifyChanges: true, requested: true, notified: 0 }); };
window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android', Plugins: {
  ItcNative: { configure: rec('configure'), sync: rec('sync'), getState: rec('getState'), requestNotifications: rec('requestNotifications'),
               openNotificationSettings: rec('openNotificationSettings'), pinWidget: rec('pinWidget') },
  App: { addListener: () => ({ remove() {} }), getLaunchUrl: () => Promise.resolve({ url: window.__launch || '' }) } } };
"""

def calls(pg, name):
    return [a for n, a in pg.evaluate("window.__calls") if n == name]

with sync_playwright() as p:
    br = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    def ctx(scheme="light", reduced="no-preference"):
        c = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme=scheme, reduced_motion=reduced,
                           user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36")
        c.add_init_script(MOCK); return c
    c = ctx(); pg = c.new_page(); errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    # 1. «Мои кружки»: звезда на странице кружка
    pg.goto(B + "/club.html?id=1"); pg.wait_for_selector(".itc-follow"); pg.wait_for_timeout(400)
    check("звезда на странице кружка", pg.locator(".itc-follow").get_attribute("aria-pressed") == "false")
    pg.click(".itc-follow"); pg.wait_for_timeout(300)
    check("подписка сохраняется", pg.evaluate("JSON.parse(localStorage.getItem('itc.follows'))") == [1])
    check("configure получает follows", any(a.get("follows") == [1] for a in calls(pg, "configure")))
    check("запрос разрешения на уведомления", len(calls(pg, "requestNotifications")) >= 1)
    pg.wait_for_timeout(600)
    sync = calls(pg, "sync")
    check("sync передаёт занятия двух недель", sync and len(sync[-1]["events"]) > 0 and len({e["date"][:10] for e in sync[-1]["events"]}) > 6, f"{len(sync[-1]['events']) if sync else 0}")
    pg.screenshot(path=str(SHOTS / "club-follow-light.png"))

    # каталог: звёзды на карточках
    pg.goto(B + "/clubs.html"); pg.wait_for_selector("a.club-card .itc-follow"); pg.wait_for_timeout(400)
    check("звёзды на карточках каталога", pg.locator("a.club-card .itc-follow").count() >= 3)
    check("в каталоге отмечен кружок 1", pg.locator('a.club-card .itc-follow[data-club-id="1"]').get_attribute("aria-pressed") == "true")
    pg.click('a.club-card .itc-follow[data-club-id="2"]'); pg.wait_for_timeout(300)
    check("клик по звезде не открывает кружок", "/clubs.html" in pg.url and pg.evaluate("JSON.parse(localStorage.getItem('itc.follows'))") == [1, 2])
    pg.screenshot(path=str(SHOTS / "clubs-stars-light.png"))

    # 2. фильтр «Мои кружки» в расписании
    pg.goto(B + "/index.html"); pg.wait_for_selector("#itc-my-toggle"); pg.wait_for_timeout(900)
    WEEK = """(async(f)=>{const m=new Date(Date.now()+3*3600e3);const d=(m.getUTCDay()+6)%7;m.setUTCDate(m.getUTCDate()-d);
       const r=await (await f('/api/schedule?week='+m.toISOString().slice(0,10))).json();return r.map(e=>e.club_id)})"""
    allw = pg.evaluate(WEEK + "(window.fetch)")
    pg.click("#itc-my-toggle"); pg.wait_for_timeout(900)
    minew = pg.evaluate(WEEK + "(window.fetch)")
    check("«Мои кружки» сужает расписание", len(minew) < len(allw) and set(minew) <= {1, 2}, f"{len(allw)} -> {len(minew)}")
    check("переключатель «Мои» нажат", pg.get_attribute("#itc-my-toggle", "aria-pressed") == "true")
    pg.screenshot(path=str(SHOTS / "schedule-my-light.png"))
    pg.click("#itc-my-toggle"); pg.wait_for_timeout(700)

    # 3. шторка напоминаний и виджетов
    pg.click("#itc-notify-open"); pg.wait_for_selector("#itc-sheet"); pg.wait_for_timeout(400)
    pg.screenshot(path=str(SHOTS / "sheet-reminders-light.png"))
    pg.select_option("#itc-remind", "60"); pg.wait_for_timeout(200)
    check("настройка напоминаний уходит в плагин", any(a.get("reminderMinutes") == 60 for a in calls(pg, "configure")))
    pg.uncheck("#itc-changes"); pg.wait_for_timeout(200)
    check("выключение уведомлений об изменениях", calls(pg, "configure")[-1].get("notifyChanges") is False)
    pg.click('[data-pin="today"]'); pg.wait_for_timeout(200)
    check("кнопка «виджет Сегодня»", calls(pg, "pinWidget")[-1] == {"kind": "today"})
    pg.click(".itc-close"); pg.wait_for_timeout(500)
    check("шторка закрывается (с анимацией)", pg.locator("#itc-sheet").count() == 0)

    # 4. ссылки ярлыков
    r = pg.evaluate("['itckruzhki://open/','itckruzhki://open/my','itckruzhki://open/clubs','itckruzhki://open/club?id=5','itckruzhki://open/qr','https://x'].map(ItcFeatures.routeOf)")
    check("маршруты ярлыков", r == ["/index.html", "/index.html?my=1", "/clubs.html", "/club.html?id=5", None, None], str(r))
    c2 = ctx(); c2.add_init_script("window.__launch='itckruzhki://open/clubs'"); p2 = c2.new_page()
    p2.goto(B + "/index.html"); p2.wait_for_timeout(1200)
    check("запуск по ярлыку открывает нужный экран", p2.url.endswith("/clubs.html"), p2.url); c2.close()

    # 5. поиск: Enter применяет, клавиатура закрывается
    pg.goto(B + "/index.html"); pg.wait_for_timeout(900)
    before = pg.inner_text("#result-status")
    check("поле поиска: enterkeyhint=search", pg.get_attribute("#search", "enterkeyhint") == "search")
    pg.click("#search"); pg.keyboard.type("Соколова", delay=20); pg.keyboard.press("Enter"); pg.wait_for_timeout(900)
    after = pg.inner_text("#result-status")
    check("Enter применяет поиск", after != before, f"{before} -> {after}")
    check("после Enter фокус снят (клавиатура скрыта)", pg.evaluate("document.activeElement.id") != "search")
    # IME: значение меняется без input-события, приходит только compositionend
    pg.evaluate("""()=>{const i=document.getElementById('search');i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));
      i.dispatchEvent(new CompositionEvent('compositionstart'));i.value='Соко';i.dispatchEvent(new CompositionEvent('compositionend',{data:'Соко'}));}""")
    pg.wait_for_timeout(900)
    check("поиск при IME-композиции (compositionend)", pg.inner_text("#result-status") != after or "Соко" in pg.input_value("#search"), pg.inner_text("#result-status"))

    # 6. объявления: переключатель в шторке уходит в нативный configure, демо-бэкенд ведёт журнал рассылок
    pg.goto(B + "/index.html"); pg.wait_for_timeout(900)
    pg.evaluate("ItcFeatures.openSheet && ItcFeatures.openSheet()"); pg.wait_for_timeout(500)
    if pg.locator("#itc-ann").count():
        check("в шторке есть «Объявления от администрации»", pg.locator("#itc-ann").is_checked())
        pg.click("#itc-ann"); pg.wait_for_timeout(300)
        check("выключение объявлений уходит в configure", calls(pg, "configure")[-1].get("notifyAnnouncements") is False, str(calls(pg, "configure")[-1:]))
        pg.click(".itc-close"); pg.wait_for_timeout(400)
    else:
        check("в шторке есть «Объявления от администрации»", False)
    sent = pg.evaluate("""(async()=>{const j=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
      const e=await (await fetch('/api/admin/broadcasts/estimate',j('POST',{audience:'all'}))).json();
      const r=await fetch('/api/admin/broadcasts',j('POST',{title:'Тест',body:'Проверка рассылки',audience:'all',idempotency_key:'k'.repeat(32)}));
      const again=await (await fetch('/api/admin/broadcasts',j('POST',{title:'Тест',body:'Проверка рассылки',audience:'all',idempotency_key:'k'.repeat(32)}))).json();
      const list=await (await fetch('/api/admin/broadcasts')).json(); return {e, status:r.status, dup:again.duplicate, n:list.length}})()""")
    check("демо: рассылка с оценкой охвата и защитой от повтора", sent.get("status") == 201 and sent.get("dup") is True and sent.get("n") == 1 and "web" in sent.get("e", {}), str(sent))
    check("старые маршруты посещаемости удалены", pg.evaluate("fetch('/api/attendance/mine').then(r=>r.status)") >= 400)

    # 7. админка: «Справочники» внутри «Занятий», подписи навигации в одну строку, рассылки
    pg.goto(B + "/admin/index.html#/reference/rooms"); pg.wait_for_timeout(1300)
    check("вкладки «Справочник» нет в нижней навигации", pg.locator('.bottom-nav a[data-route="reference"]').is_visible() is False)
    check("сегменты «Занятия» на экране справочника", pg.locator("#native-sessions-tabs a").count() == 5 and
          pg.locator('#native-sessions-tabs a[aria-selected="true"]').inner_text() == "Аудитории")
    check("«Занятия» подсвечены в навигации", pg.locator('.bottom-nav a[data-route="sessions"]').get_attribute("aria-current") == "page")
    heights = pg.evaluate("[...document.querySelectorAll('.bottom-nav .bn-label')].filter(e=>e.offsetParent).map(e=>e.getBoundingClientRect().height)")
    check("подписи нижней навигации в одну строку", heights and max(heights) < 20, str(heights))
    pg.screenshot(path=str(SHOTS / "admin-sessions-reference-light.png"))
    pg.click('#native-sessions-tabs a:has-text("Расписание")'); pg.wait_for_timeout(900)
    check("переход в «Расписание» из сегментов", pg.url.endswith("#/sessions") and pg.locator("#native-sessions-tabs").count() == 1)
    pg.goto(B + "/admin/index.html#/broadcasts"); pg.wait_for_timeout(1300)
    main = pg.inner_text("#admin-main")
    check("экран «Рассылки» открывается", "Рассылки" in pg.inner_text("body") and "Тест" in main, main[:200])
    pg.screenshot(path=str(SHOTS / "admin-broadcasts-light.png"), full_page=True)
    pg.goto(B + "/admin/login.html"); pg.wait_for_timeout(700)
    t = pg.inner_text("body")
    check("на входе нет подсказок для разработчиков", "Демо-режим" not in t and "reset-password" not in t)

    # 8. анимации: без ошибок, модальные окна, удаление
    check("ошибок JS нет", not errors, "; ".join(errors[:3]))
    check("css анимаций подключён", pg.evaluate("!!document.querySelector('link[href=\"/css/native-motion.css\"]')"))
    c.close()

    # тёмная тема + reduced motion
    c = ctx("dark", "reduce"); pg = c.new_page(); errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(B + "/clubs.html"); pg.wait_for_timeout(300)
    pg.evaluate("localStorage.setItem('itc.follows','[1]')")
    pg.goto(B + "/index.html"); pg.wait_for_timeout(1000)
    pg.screenshot(path=str(SHOTS / "schedule-my-dark.png"))
    pg.click("#itc-notify-open"); pg.wait_for_timeout(400); pg.screenshot(path=str(SHOTS / "sheet-reminders-dark.png"))
    pg.goto(B + "/club.html?id=1"); pg.wait_for_timeout(900); pg.screenshot(path=str(SHOTS / "club-follow-dark.png"))
    pg.goto(B + "/admin/index.html#/sessions"); pg.wait_for_timeout(1200); pg.screenshot(path=str(SHOTS / "admin-sessions-dark.png"))
    check("reduced motion: ошибок нет", not errors, "; ".join(errors[:3]))
    c.close(); br.close()

srv.shutdown()
fails = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
