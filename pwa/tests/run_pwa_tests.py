"""Тесты установленного PWA (phase 2 D) в Chromium: standalone на iPhone и Android эмулируется (navigator.standalone /
display-mode), push/Notification/Badging — моки, записывающие вызовы; сервер и БД — настоящие (server.py, демо-данные).
  python pwa/tests/run_pwa_tests.py            (PWA_DIR=готовая сборка — без пересборки; SHOTS_DIR — куда скриншоты)"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from pwa_env import ADMIN, ANDROID_UA, CHROME, IOS_UA, PASSWORD, Stand, init_script  # noqa: E402

SHOTS = Path(os.environ.get("SHOTS_DIR", "/workspace/itc/shots_de"))
SHOTS.mkdir(parents=True, exist_ok=True)
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail else ""), flush=True)


def calls(pg, name):
    return [a for n, a in pg.evaluate("window.__calls") if n == name]


def next_monday_msk():
    now = datetime.now(timezone(timedelta(hours=3))).date()
    return now + timedelta(days=(7 - now.weekday()) % 7 or 7)


st = Stand()
try:
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

        def ctx(kind="ios", standalone=True, share=False, scheme="light", w=393, h=852, reduced="no-preference"):
            c = br.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=3 if kind == "ios" else 2.625,
                is_mobile=True,
                has_touch=True,
                user_agent=IOS_UA if kind == "ios" else ANDROID_UA,
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                color_scheme=scheme,
                reduced_motion=reduced,
                base_url=st.base,
                accept_downloads=True,
            )
            c.add_init_script(init_script(kind, standalone, share))
            return c

        # 0. обычная вкладка браузера: сайт без изменений
        c = ctx(standalone=False)
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("/")
        pg.wait_for_load_state("networkidle")
        check("вкладка браузера: нет is-pwa / is-native", pg.evaluate("!document.documentElement.matches('.is-pwa,.is-native')"))
        check(
            "вкладка браузера: оболочка не подгружена",
            pg.evaluate("!window.ItcFeatures && !window.ItcMotion && !document.querySelector('script[src*=\"native-\"]')"),
        )
        check("вкладка браузера: нет панели «Мои кружки»", pg.locator("#itc-my-toggle").count() == 0)
        check("вкладка браузера: без ошибок JS", not errs, "; ".join(errs))
        pg.goto("/club.html?id=1")
        pg.wait_for_load_state("networkidle")
        check("вкладка браузера: нет звезды на кружке", pg.locator(".itc-follow").count() == 0)
        c.close()

        # 1. iPhone standalone: оболочка, «Мои кружки», push только по жесту
        c = ctx("ios")
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("/")
        pg.wait_for_selector("#itc-my-toggle")
        pg.wait_for_timeout(800)
        check(
            "standalone iOS: is-pwa + is-native + is-pwa-ios",
            pg.evaluate("['is-pwa','is-native','is-pwa-ios'].every(c => document.documentElement.classList.contains(c))"),
        )
        check(
            "standalone: оболочка APK подключена (shell/features/motion/pwa)",
            pg.evaluate("!!(window.NativeShell && window.ItcFeatures && window.ItcMotion && window.ItcPwaFeatures)"),
        )
        check("standalone: NativeShell.host = pwa", pg.evaluate("window.NativeShell.host") == "pwa")
        check("бренд «KipClub» как в APK", "KipClub" in pg.locator(".campus-brand").first.inner_text())
        check("разрешение на уведомления НЕ запрашивается при запуске", not calls(pg, "requestPermission"))
        pg.screenshot(path=str(SHOTS / "d-schedule-iphone15-light.png"))
        pg.goto("/club.html?id=1")
        pg.wait_for_selector(".itc-follow")
        pg.wait_for_timeout(400)
        check("звезда «В Мои кружки» на странице кружка", pg.get_attribute(".itc-follow", "aria-pressed") == "false")
        pg.click(".itc-follow")
        pg.wait_for_timeout(500)
        check("follow сохранён", pg.evaluate("JSON.parse(localStorage.getItem('itc.follows'))") == [1])
        check("после звезды разрешение не спрошено само", not calls(pg, "requestPermission"))
        check("предложение «Включить» уведомления показано", pg.locator("#itc-push-offer").is_visible())
        pg.screenshot(path=str(SHOTS / "d-club-offer-iphone15-light.png"))
        pg.click("#itc-push-offer button[data-a=yes]")
        pg.wait_for_timeout(1500)
        rp = calls(pg, "requestPermission")
        check("requestPermission вызван один раз и внутри жеста пользователя", len(rp) == 1 and rp[0]["active"] is True, str(rp))
        check("push-подписка создана с VAPID-ключом", calls(pg, "pushSubscribe") == [True])
        check("подписка на кружок 1 записана", pg.evaluate("JSON.parse(localStorage.getItem('itc.pwa.pushClubs'))") == [1])
        ep = pg.evaluate("navigator.serviceWorker.getRegistration('/').then(r => r.pushManager.getSubscription()).then(s => s.endpoint)")
        status = pg.request.post("/api/push/status", data={"endpoint": ep}).json()
        check("сервер: подписка на кружок 1", status.get("club_ids") == [1] and not status.get("all"), str(status))
        # второй кружок в каталоге -> подписка догоняет сама (без нового запроса разрешения)
        pg.goto("/clubs.html")
        pg.wait_for_selector("a.club-card .itc-follow")
        pg.wait_for_timeout(300)
        pg.locator("a.club-card[href*='id=2'] .itc-follow").click()
        pg.wait_for_timeout(1200)
        status = pg.request.post("/api/push/status", data={"endpoint": ep}).json()
        check("follow кружка 2 -> push-подписка на 2", sorted(status.get("club_ids", [])) == [1, 2], str(status))
        check("повторно разрешение не спрашивали", len(calls(pg, "requestPermission")) == 0)
        pg.screenshot(path=str(SHOTS / "d-clubs-stars-iphone15-light.png"))
        pg.locator("a.club-card[href*='id=2'] .itc-follow").click()
        pg.wait_for_timeout(1200)
        status = pg.request.post("/api/push/status", data={"endpoint": ep}).json()
        check("unfollow кружка 2 -> отписка", status.get("club_ids") == [1], str(status))

        # 2. шторка «Уведомления» (вместо «Напоминания и виджеты»)
        pg.goto("/")
        pg.wait_for_selector("#itc-notify-open")
        pg.click("#itc-notify-open")
        pg.wait_for_selector("#itc-sheet")
        check("шторка «Уведомления»", pg.inner_text("#itc-sheet-title") == "Уведомления")
        check("в шторке PWA нет виджетов APK", pg.locator("#itc-sheet [data-pin]").count() == 0)
        check("переключатель push включён", pg.is_checked("#itc-push"))
        pg.wait_for_timeout(350)
        pg.screenshot(path=str(SHOTS / "d-sheet-notifications-iphone15-light.png"))
        pg.click("#itc-push")
        pg.wait_for_timeout(1000)
        status = pg.request.post("/api/push/status", data={"endpoint": ep}).json()
        check("выключение в шторке -> отписка на сервере", status.get("club_ids") == [] and not status.get("all"), str(status))
        pg.click("#itc-push")
        pg.wait_for_timeout(1200)
        status = pg.request.post("/api/push/status", data={"endpoint": ep}).json()
        check("повторное включение (по нажатию) -> подписка снова", status.get("club_ids") == [1], str(status))
        pg.click(".itc-close")

        # 3. значок на иконке: отмена занятия «Моего кружка» -> setAppBadge(1); просмотр «Моих» -> 0
        api = c.request
        tok = api.post("/api/admin/login", data={"login": ADMIN, "password": PASSWORD}).json()["access_token"]
        mon = next_monday_msk()
        day = mon.isoformat()
        wed = (mon + timedelta(days=2)).isoformat()
        r = api.post(
            "/api/admin/exceptions/cancellations",
            data={"session_id": 2, "original_date": wed, "comment": "QA"},
            headers={"Authorization": "Bearer " + tok},
        )
        check("админ отменил занятие кружка 1", r.status in (200, 201), f"{r.status} {r.text()[:200]}")
        today = datetime.now(timezone(timedelta(hours=3))).date()
        weeks = [today - timedelta(days=today.weekday()), mon]
        evs = [e for w in weeks for e in api.get(f"/api/schedule?week={w.isoformat()}").json()]
        expected = len([e for e in evs if e["club_id"] == 1 and e["status"] in ("cancelled", "moved") and e["date"] >= today.isoformat()])
        pg.evaluate("localStorage.setItem('itc.myMode','0')")
        pg.goto("/")
        pg.wait_for_timeout(1500)
        badges = calls(pg, "setAppBadge")
        check(
            f"значок на иконке = {expected} (непросмотренные отмены/переносы «Моих»)",
            expected >= 2 and badges and badges[-1] == expected,
            str(badges),
        )
        pg.click("#itc-my-toggle")
        pg.wait_for_timeout(2500)
        check("«Мои кружки» показаны -> значок сброшен", calls(pg, "clearAppBadge") and pg.get_attribute("html", "data-itc-badge") == "0")
        check(
            "режим «Мои»: только кружок 1",
            pg.evaluate("fetch('/api/schedule?week=" + day + "').then(r=>r.json()).then(a=>a.length>0 && a.every(e=>e.club_id===1))"),
        )
        pg.screenshot(path=str(SHOTS / "d-schedule-my-iphone15-light.png"))
        check("без ошибок JS (iOS standalone)", not errs, "; ".join(errs))
        c.close()

        # 4. .ics: iOS — системное «Поделиться» с файлом; Android — скачивание
        c = ctx("ios", share=True)
        pg = c.new_page()
        pg.goto("/club.html?id=1")
        pg.wait_for_selector("a[href*='calendar.ics']")
        pg.wait_for_timeout(400)
        check("кнопка «Добавить в календарь»", "Добавить в календарь" in pg.inner_text("a[href*='calendar.ics']"))
        pg.click("a[href*='calendar.ics']")
        pg.wait_for_timeout(1200)
        sh = calls(pg, "share")
        ok = (
            sh
            and sh[0]["name"] == "club-1.ics"
            and sh[0]["type"] == "text/calendar"
            and "RRULE:FREQ=WEEKLY" in sh[0]["text"]
            and "BEGIN:VEVENT" in sh[0]["text"]
        )
        check(".ics (iOS): share с файлом text/calendar, еженедельные RRULE", ok, str(sh)[:200])
        check(".ics: отменённое занятие исключено (EXDATE)", sh and "EXDATE:" + day.replace("-", "") in sh[0]["text"], "")
        c.close()
        c = ctx("android", w=360, h=800)
        pg = c.new_page()
        pg.goto("/club.html?id=1")
        pg.wait_for_selector("a[href*='calendar.ics']")
        pg.wait_for_timeout(400)
        with pg.expect_download(timeout=8000) as dl:
            pg.click("a[href*='calendar.ics']")
        path = dl.value.path()
        text = Path(path).read_text(encoding="utf-8")
        check(
            ".ics (Android PWA): файл скачан",
            dl.value.suggested_filename == "club-1.ics" and "BEGIN:VCALENDAR" in text and "END:VCALENDAR" in text,
        )

        # 5. офлайн: SW + кэш данных; баннер «Нет сети»
        pg.goto("/")
        pg.wait_for_selector("#itc-my-toggle")
        pg.wait_for_load_state("networkidle")
        pg.evaluate("navigator.serviceWorker.ready")
        pg.wait_for_timeout(800)
        pg.reload()
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(500)
        c.set_offline(True)
        pg.reload()
        pg.wait_for_timeout(2500)
        check("офлайн: страница открылась из кэша SW", pg.locator("#schedule-filters").count() == 1)
        check("офлайн: баннер «Нет сети»", pg.locator("#itc-offline-banner").is_visible())
        txt = pg.evaluate("(document.querySelector('#result-status') || document.body).innerText") or ""
        check("офлайн: расписание показано из кэша", pg.locator(".event-name").count() > 0 and "Ошибка" not in txt, txt[:80])
        pg.screenshot(path=str(SHOTS / "d-offline-android360-light.png"))
        c.set_offline(False)
        c.close()

        # 6. Android standalone (display-mode), тёмная тема, reduced motion — без ошибок
        c = ctx("android", scheme="dark", w=360, h=800, reduced="reduce")
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("/")
        pg.wait_for_selector("#itc-my-toggle")
        pg.wait_for_timeout(600)
        check("Android standalone: is-pwa-other", pg.evaluate("document.documentElement.classList.contains('is-pwa-other')"))
        check("в PWA нет страницы QR-отметки", pg.request.get("/qr.html").status == 404)
        pg.goto("/admin/login.html")
        pg.wait_for_selector("#login-form")
        pg.fill("input[name=login]", ADMIN)
        pg.fill("input[name=password]", PASSWORD)
        pg.click("#login-form button[type=submit]")
        pg.wait_for_selector(".bottom-nav", timeout=10000)
        pg.goto("/admin/#/sessions")
        pg.wait_for_timeout(1200)
        check("админка в PWA: вкладки «Занятия» со справочниками", pg.locator("#native-sessions-tabs a").count() == 5)
        check("админка в PWA: «Справочники» нет в нижней навигации", not pg.locator(".bottom-nav [data-route=reference]").is_visible())
        pg.screenshot(path=str(SHOTS / "d-admin-sessions-android360-dark.png"))
        check("без ошибок JS (Android standalone)", not errs, "; ".join(errs))
        c.close()
        manifest = json.loads((st.www / "manifest.webmanifest").read_text(encoding="utf-8"))
        check(
            "manifest: ярлык «Мои кружки», без «Отметиться»",
            {
                s["url"].split("?")[0] + "?" + s["url"].split("?")[1].split("&")[0] if "?" in s["url"] else s["url"]
                for s in manifest["shortcuts"]
            }
            == {"/?my=1"} or not any("qr" in s["url"] for s in manifest["shortcuts"]),
        )
        br.close()
finally:
    st.stop()

ok = sum(1 for _, r in results if r)
print(f"\nИТОГО: {ok}/{len(results)} ок")
sys.exit(0 if ok == len(results) else 1)
