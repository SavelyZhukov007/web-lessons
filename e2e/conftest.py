"""E2E в настоящем Chromium (Playwright). Поднимает server.py на временной БД. Пропускается, если playwright/Chromium не установлены:
    pip install -r requirements-dev.txt && playwright install chromium
Запуск: python -m pytest e2e -q"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADMIN_LOGIN, ADMIN_PASSWORD = "admin", "Demo-Pass-2026!"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_cli(env, *args, stdin=None):
    return subprocess.run([sys.executable, str(ROOT / "server.py"), *args], cwd=ROOT, env=env, input=stdin, text=True, capture_output=True, check=True, timeout=120)


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    env = {**os.environ, "CLUBS_SCHEDULE_DB_PATH": str(tmp / "e2e.sqlite3"), "ENV": "development", "JWT_SECRET": "e2e-" + "s" * 40,
           "VAPID_KEYS_FILE": str(tmp / "vapid.json"), "APP_LOGS_DIR": str(tmp / "client-logs"), "SCRYPT_LOG_N": "12"}
    env.pop("CLUBS_USE_CREATE_ALL", None)
    run_cli(env, "build", "web", "--out", str(tmp / "web"))
    env["CLUBS_FRONTEND_DIR"] = str(tmp / "web")
    run_cli(env, "seed", "--file", "data/demo-data.json")
    run_cli(env, "admin", "create", ADMIN_LOGIN, "--password-stdin", stdin=ADMIN_PASSWORD + "\n")
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(ROOT / "server.py"), "serve", "--port", str(port), "--no-reload"], cwd=ROOT, env=env,
                            stdout=(tmp / "server.log").open("w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/readyz", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("сервер не поднялся: " + (tmp / "server.log").read_text())
    yield base
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="session")
def browser():
    if sync_playwright is None:
        pytest.skip("playwright не установлен")
    with sync_playwright() as p:
        try:
            # E2E_CHROME — путь к системному Chrome/Chromium, если `playwright install chromium` не делали; E2E_NO_SANDBOX=1 — в контейнерах
            kwargs = {"executable_path": os.environ["E2E_CHROME"]} if os.getenv("E2E_CHROME") else {}
            if os.getenv("E2E_NO_SANDBOX"):
                kwargs["args"] = ["--no-sandbox"]
            b = p.chromium.launch(**kwargs)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium недоступен: {exc}")
        yield b
        b.close()


class Page:
    """Страница + сбор ошибок консоли/CSP."""

    def __init__(self, page):
        self.page = page
        self.errors: list[str] = []
        page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        # 4xx/5xx на статике — ошибка; 401 на /api/admin/status и /refresh допустим (проверка «уже вошёл?» на странице входа)
        page.on("response", lambda r: self.errors.append(f"{r.status} {r.url}") if r.status >= 400 and not r.url.endswith(("/api/admin/status", "/api/admin/login", "/api/admin/refresh")) else None)

    def __getattr__(self, name):
        return getattr(self.page, name)


@pytest.fixture
def new_page(browser, server):
    contexts = []

    def make(width=1366, height=768, **kw):
        ctx = browser.new_context(viewport={"width": width, "height": height}, base_url=server, locale="ru-RU", timezone_id="Europe/Moscow", **kw)
        contexts.append(ctx)
        return Page(ctx.new_page())

    yield make
    for c in contexts:
        c.close()


def do_login(page, login=ADMIN_LOGIN, password=ADMIN_PASSWORD):
    page.goto("/admin/login.html")
    page.fill("#login", login)
    page.fill("#password", password)
    page.click("button[type=submit]")


@pytest.fixture
def admin(new_page):
    page = new_page()
    do_login(page)
    page.wait_for_url("**/admin/")
    page.wait_for_selector("#view-title")
    return page
