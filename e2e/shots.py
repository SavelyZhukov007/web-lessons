"""Скриншоты ключевых экранов в светлой/тёмной теме и в android/ios-стилях.
python e2e/shots.py http://127.0.0.1:8000 admin 'пароль' out_dir   (нужен запущенный сервер с данными: server.py seed --file data/demo-data.json)"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base, login, password, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)

PUBLIC = [("schedule", "/"), ("clubs", "/clubs.html"), ("club", "/club.html?id=1"), ("install", "/install")]
ADMIN = [("admin-login", None), ("admin-dashboard", "#/"), ("admin-clubs", "#/clubs"), ("admin-sessions", "#/sessions"),
         ("admin-exceptions", "#/exceptions"), ("admin-reference", "#/reference/rooms")]
VARIANTS = [  # (имя, платформа, тема, viewport, mobile)
    ("desktop-light", "desktop", "light", (1366, 768), False),
    ("desktop-dark", "desktop", "dark", (1366, 768), False),
    ("mobile-light", "desktop", "light", (390, 844), True),
    ("mobile-dark", "desktop", "dark", (390, 844), True),
    ("android-dark", "android", "dark", (390, 844), True),
    ("android-light", "android", "light", (390, 844), True),
    ("ios-light", "ios", "light", (390, 844), True),
    ("ios-dark", "ios", "dark", (390, 844), True),
]
kw = {"executable_path": os.environ["E2E_CHROME"], "args": ["--no-sandbox"]} if os.getenv("E2E_CHROME") else {}

with sync_playwright() as p:
    browser = p.chromium.launch(**kw)
    for name, platform, theme, (w, h), mobile in VARIANTS:
        ctx = browser.new_context(viewport={"width": w, "height": h}, base_url=base, is_mobile=mobile, has_touch=mobile, locale="ru-RU", service_workers="block",
                                  timezone_id="Europe/Moscow", device_scale_factor=2 if mobile else 1)
        ctx.add_init_script(f"try{{localStorage.setItem('clubs.prefs', JSON.stringify({{theme:'{theme}',accent:'brick',textSize:'normal'}}))}}catch(e){{}}")
        page = ctx.new_page()
        for key, path in PUBLIC:
            page.goto(f"{path}{'&' if '?' in path else '?'}platform={platform}")
            page.wait_for_load_state("load"); page.wait_for_timeout(600)
            page.wait_for_timeout(400)
            page.screenshot(path=str(out / f"{key}__{name}.png"), full_page=False)
        page.goto(f"/admin/login.html?platform={platform}")
        page.wait_for_load_state("load"); page.wait_for_timeout(600)
        page.screenshot(path=str(out / f"admin-login__{name}.png"))
        page.fill("#login", login); page.fill("#password", password); page.click("button[type=submit]")
        page.wait_for_selector(".stat-card")
        for key, hashv in ADMIN[1:]:
            page.evaluate("h => { location.hash = h }", hashv)
            page.wait_for_timeout(700)
            page.wait_for_selector("#admin-main:not([aria-busy])")
            page.screenshot(path=str(out / f"{key}__{name}.png"))
        # диалоги
        page.evaluate("() => { location.hash = '#/sessions' }"); page.wait_for_selector("text=Добавить занятие")
        page.click("text=Добавить занятие")
        page.select_option("#f-club_id", label="Робототехника"); page.select_option("#f-room_id", index=1); page.select_option("#f-weekday", value="1")
        page.fill("#f-start_time", "15:30"); page.fill("#f-end_time", "16:00"); page.click("dialog button[type=submit]")
        page.wait_for_selector("dialog .conflict-box"); page.wait_for_timeout(300)
        page.screenshot(path=str(out / f"admin-conflict-dialog__{name}.png"))
        page.keyboard.press("Escape")
        page.click("[data-settings-button]"); page.wait_for_selector("#settings-dialog[open]"); page.wait_for_timeout(300)
        page.screenshot(path=str(out / f"admin-settings__{name}.png"))
        ctx.close()
    browser.close()
print(len(list(out.glob("*.png"))), "screenshots")
