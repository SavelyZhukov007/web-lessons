"""Тесты web-слоя Android-клиента (shim + settings) в Chromium. Нужны: pip install playwright requests uvicorn fastapi sqlalchemy,
Chrome (CHROME_PATH), каталог с рабочей копией проекта и БД с демо-данными (PROJECT_COPY), собранный www/ (npm run prepare-web).
Эмулируем WebView Capacitor: origin http://localhost:9000 (статический www/) -> API на http://127.0.0.1:PORT (другой origin)."""
import os, sys, shutil, subprocess, time, json, tempfile, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright
import requests

HERE = Path(__file__).resolve().parent.parent
PROJECT = HERE.parent  # корень проекта (feature): CORS включается переменной CORS_ORIGINS, патчей не нужно
DEMO_DB = Path(os.environ.get("DEMO_DB", "/workspace/itc/shotdb.sqlite3"))
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
SHOTS = Path(os.environ.get("SHOTS_DIR", "/workspace/itc/shots"))
WWW = HERE / "www"
P_CORS, P_PLAIN, P_STATIC = 48988, 48989, int(os.environ.get("STATIC_PORT", "9100"))
procs, results = [], []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail else ""))

def start_backend(dirpath, port, env_extra=None):
    env = dict(os.environ, CLUBS_SCHEDULE_DB_PATH=str(tmp / f"db{port}.sqlite3"), **(env_extra or {}))
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                         cwd=dirpath, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    for _ in range(40):
        try:
            if requests.get(f"http://127.0.0.1:{port}/api/health", timeout=1).ok: return
        except Exception: time.sleep(0.25)
    raise RuntimeError("backend не поднялся на %s" % port)

tmp = Path(tempfile.mkdtemp(prefix="shimtest_"))
plain = cors = PROJECT
for port in (P_CORS, P_PLAIN):
    shutil.copy(DEMO_DB, tmp / f"db{port}.sqlite3")
    for sub in ("create", "reset-password"):  # в демо-БД админ может уже быть
        r = subprocess.run([sys.executable, "server.py", "admin", sub, "admin", "--password-stdin"], cwd=PROJECT, input="DemoPass123!",
                           text=True, capture_output=True, env=dict(os.environ, CLUBS_SCHEDULE_DB_PATH=str(tmp / f"db{port}.sqlite3")))
        if r.returncode == 0: break
    else: raise RuntimeError(r.stderr)

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", P_STATIC), functools.partial(Q, directory=str(WWW)))
threading.Thread(target=httpd.serve_forever, daemon=True).start()

try:
    start_backend(cors, P_CORS, {"CORS_ORIGINS": f"http://localhost:{P_STATIC}"})
    start_backend(plain, P_PLAIN)
    APP = f"http://localhost:{P_STATIC}"
    CORS_URL, PLAIN_URL = f"http://127.0.0.1:{P_CORS}", f"http://127.0.0.1:{P_PLAIN}"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); reqs = []
        pg.on("request", lambda r: reqs.append(r.url))
        # 1. первый запуск -> settings
        pg.goto(APP + "/"); pg.wait_for_url("**/settings.html*")
        check("первый запуск редиректит на /settings.html", "/settings.html" in pg.url, pg.url)
        pg.screenshot(path=str(SHOTS / "apk-web-01-settings-first-launch.png"))
        # 2. нормализация
        norm = lambda v: pg.evaluate("v => { try { return AppServer.normalize(v) } catch(e) { return 'ERR:' + e.message } }", v)
        check("normalize '192.168.1.5:8000' -> http://192.168.1.5:8000", norm("192.168.1.5:8000") == "http://192.168.1.5:8000")
        check("normalize 'http://10.0.2.2:8000/' убирает слэш", norm("http://10.0.2.2:8000/") == "http://10.0.2.2:8000")
        check("normalize 'https://x.example/path?q=1' -> origin", norm("https://x.example/path?q=1") == "https://x.example")
        check("normalize '' -> ошибка", norm("").startswith("ERR:"))
        check("normalize 'ftp://a' -> ошибка", norm("ftp://a").startswith("ERR:"))
        check("normalize 'a:99999' -> ошибка порта", norm("a:99999").startswith("ERR:"))
        # 3. Проверка соединения: сервер без CORS (как в браузере) -> понятная ошибка
        pg.fill("#server-url", PLAIN_URL); pg.click("#test"); pg.wait_for_selector("#status.err, #status.ok", timeout=15000)
        txt = pg.inner_text("#status"); check("тест соединения: сервер БЕЗ CORS из браузерного origin -> ошибка с подсказкой", pg.get_attribute("#status", "class") == "err" and "0.0.0.0" in txt, txt[:90])
        # 4. мёртвый порт
        pg.fill("#server-url", "127.0.0.1:1"); pg.click("#test"); pg.wait_for_selector("#status.err", timeout=15000)
        check("тест соединения: мёртвый порт -> ошибка", True, pg.inner_text("#status")[:70])
        # 5. не тот сервер (статик на :9000 отдаёт html, CORS нет) -> ошибка
        pg.fill("#server-url", "foo bar"); pg.click("#test"); pg.wait_for_function("document.getElementById('status').className=='err'")
        check("тест соединения: мусор во вводе -> ошибка формата", "Некорректный" in pg.inner_text("#status"), pg.inner_text("#status")[:70])
        # 6. сервер с CORS -> OK
        pg.fill("#server-url", f"127.0.0.1:{P_CORS}"); pg.click("#test"); pg.wait_for_selector("#status.ok", timeout=15000)
        check("тест соединения: сервер с CORS -> OK и число кружков", "кружков: 8" in pg.inner_text("#status"), pg.inner_text("#status"))
        pg.screenshot(path=str(SHOTS / "apk-web-02-settings-test-ok.png"))
        # 7. сохранить и открыть
        mark = len(reqs); pg.click("#save"); pg.wait_for_url(APP + "/"); pg.wait_for_selector(".calendar-event", timeout=15000)
        saved = pg.evaluate("localStorage.getItem('clubs.serverUrl')")
        check("сохранение адреса в localStorage (нормализован)", saved == CORS_URL, saved)
        api_reqs = [u for u in reqs[mark:] if "/api/" in u]
        check("все /api запросы ушли на сохранённый сервер (не на origin приложения)", api_reqs and all(u.startswith(CORS_URL) for u in api_reqs), f"{len(api_reqs)} запросов, напр. {api_reqs[:1]}")
        check("расписание отрисовано через shim", pg.locator(".calendar-event").count() > 0, f"карточек: {pg.locator('.calendar-event').count()}")
        pg.screenshot(path=str(SHOTS / "apk-web-03-schedule-via-shim.png"))
        # 8. Навигация/фильтр/страницы работают
        pg.click("#next-week"); pg.wait_for_timeout(700)
        check("переключение недели работает через shim", "26" in pg.inner_text("#week-label"), pg.inner_text("#week-label"))
        gear = pg.locator("[data-settings-button]").first
        box = gear.bounding_box(); check("кнопка «Настройки» (в шапке сайта) ≥ 44px", box["height"] >= 44 and box["width"] >= 44, str(box))
        check("старой плавающей кнопки «⚙ сервер» нет (есть единый диалог настроек)", pg.locator("#app-gear").count() == 0)
        pg.goto(APP + "/clubs.html"); pg.wait_for_selector("#content a")
        check("clubs.html грузит список через shim", pg.locator("#content a").count() == 8)
        pg.click("#content a >> nth=0"); pg.wait_for_load_state("networkidle"); check("club.html?id= грузит кружок", pg.inner_text("h1") not in ("Кружок", "Кружок не найден"), pg.inner_text("h1"))
        # 9. Админка: логин из другого origin
        pg.goto(APP + "/admin/login.html"); pg.fill("input[name=login]", "admin"); pg.fill("input[name=password]", "wrongwrong1"); pg.click("#login-form button[type=submit]"); pg.wait_for_timeout(800)
        check("админ-логин: неверный пароль -> сообщение (CORS ок, тело ошибки читается)", "Неверный" in pg.inner_text("#message"), pg.inner_text("#message"))
        pg.fill("input[name=password]", "DemoPass123!"); pg.click("#login-form button[type=submit]"); pg.wait_for_url("**/admin/", timeout=15000)
        pg.wait_for_selector("#admin-main h1, #admin-main h2", timeout=15000)
        token = pg.evaluate("localStorage.getItem('clubs.adminToken')")
        cookies = [c for c in ctx.cookies() if c["name"] == "admin_session"]
        check("админ-логин в режиме приложения: Bearer-токен получен и сохранён, cookie между origin не нужны", bool(token) and not cookies, f"token={'есть' if token else 'нет'}, cookies={len(cookies)}")
        pg.wait_for_function("document.querySelector('#admin-main').innerText.length > 40", timeout=15000)
        check("админка рисуется и ходит в API по Bearer (дашборд загружен)", "ошибк" not in pg.inner_text("#admin-main").lower()[:200], pg.inner_text("#admin-main").replace("\n", " ")[:80])
        pg.goto(APP + "/admin/#/clubs"); pg.wait_for_selector("table.data tbody tr, .data-card", timeout=15000)
        check("список кружков в админке загружается через сервер", pg.locator("table.data tbody tr").count() > 0)
        # 9b. access-токен «протух» -> тихая ротация refresh-токена из localStorage (Bearer, без cookie)
        old_refresh = pg.evaluate("localStorage.getItem('clubs.adminRefresh')")
        pg.evaluate("localStorage.setItem('clubs.adminToken', 'expired.invalid.token')")
        pg.goto(APP + "/clubs.html"); pg.goto(APP + "/admin/#/clubs"); pg.wait_for_selector("table.data tbody tr, .data-card", timeout=15000)
        new_refresh = pg.evaluate("localStorage.getItem('clubs.adminRefresh')")
        check("приложение: просроченный access обновляется refresh-токеном (ротация), админка остаётся открытой",
              "/login.html" not in pg.url and bool(old_refresh) and new_refresh and new_refresh != old_refresh and pg.evaluate("localStorage.getItem('clubs.adminToken')") != "expired.invalid.token", f"{pg.url} old={old_refresh and old_refresh[:8]} new={new_refresh and new_refresh[:8]}")
        # 10. смена сервера через единый диалог «Настройки»
        pg.goto(APP + "/"); pg.wait_for_selector("[data-settings-button]"); pg.click("[data-settings-button] >> nth=0"); pg.wait_for_selector("#settings-server")
        check("в диалоге «Настройки» есть раздел «Сервер» с текущим адресом", pg.input_value("#settings-server") == CORS_URL, pg.input_value("#settings-server"))
        pg.fill("#settings-server", "127.0.0.1:1"); pg.click("dialog >> text=Сохранить"); pg.wait_for_function("document.querySelector('#settings-server').closest('section').innerText.includes('не сохранён')", timeout=15000)
        check("недоступный адрес в диалоге: адрес НЕ сохранён", pg.evaluate("localStorage.getItem('clubs.serverUrl')") == CORS_URL)
        pg.screenshot(path=str(SHOTS / "apk-web-04-settings-change.png"))
        pg.goto(APP + "/settings.html")
        pg.click("#reset"); pg.wait_for_url("**/settings.html?first=1")
        check("«Забыть сервер» очищает localStorage и ведёт на первый запуск", pg.evaluate("localStorage.getItem('clubs.serverUrl')") is None)
        # 11. Сохранить недоступный
        pg.fill("#server-url", "127.0.0.1:1"); pg.click("#save"); pg.wait_for_selector("#status.err", timeout=15000)
        check("недоступный сервер: «Сохранить» не сохраняет, показывается «Всё равно сохранить»", pg.is_visible("#force") and pg.evaluate("localStorage.getItem('clubs.serverUrl')") is None)
        pg.click("#force"); pg.wait_for_url(APP + "/"); pg.wait_for_selector(".schedule-state", timeout=20000)
        check("экран ошибки сети при недоступном сервере (штатный от api.js)", "связаться" in pg.inner_text("#content") or "Не получилось" in pg.inner_text("#content"), pg.inner_text("#content").replace("\n", " ")[:90])
        pg.screenshot(path=str(SHOTS / "apk-web-05-offline-server-error.png"))
        # 12. сборка с предзаданным сервером (build android --server-url): первый запуск без экрана настроек
        ctx.close()
        prep = lambda extra: subprocess.run(["node", str(HERE / "scripts" / "prepare-web.mjs")], cwd=HERE, check=True, capture_output=True, env=dict(os.environ, **extra))
        prep({"APP_DEFAULT_SERVER": CORS_URL})
        try:
            ctx2 = b.new_context(viewport={"width": 390, "height": 844}); pg2 = ctx2.new_page()
            pg2.goto(APP + "/"); pg2.wait_for_selector(".calendar-event", timeout=20000)
            check("APP_DEFAULT_SERVER: первый запуск сразу показывает расписание, без экрана настроек", "settings.html" not in pg2.url and pg2.evaluate("localStorage.getItem('clubs.serverUrl')") is None, pg2.url)
            pg2.click("[data-settings-button] >> nth=0"); pg2.wait_for_selector("#settings-server")
            check("APP_DEFAULT_SERVER виден в диалоге «Настройки» и его можно сменить", pg2.input_value("#settings-server") == CORS_URL)
            ctx2.close()
        finally:
            prep({"APP_DEFAULT_SERVER": ""})
        b.close()
finally:
    for pr in procs: pr.terminate()
    httpd.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
bad = [r for r in results if not r[1]]
print(f"\nИТОГО: {len(results)-len(bad)}/{len(results)} ок"); sys.exit(1 if bad else 0)
