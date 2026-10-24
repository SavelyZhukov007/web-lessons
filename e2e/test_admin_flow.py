
import pytest

from .conftest import ADMIN_PASSWORD, do_login

pytest.importorskip("playwright")


def go(page, route):
    page.evaluate("r => location.hash = r", f"#/{route}")
    page.wait_for_function("r => document.querySelector('#view-title') && document.querySelector('[aria-current=page][data-route]')?.dataset.route === r", arg=route.split("/")[0])
    page.wait_for_selector("#admin-main:not([aria-busy])")


def test_unauthenticated_admin_redirects_to_login(new_page):
    page = new_page()
    page.goto("/admin/")
    page.wait_for_url("**/admin/login.html")
    assert page.locator("h1").inner_text() == "Вход для сотрудников"


def test_login_wrong_password_then_ok(new_page):
    page = new_page()
    do_login(page, password="wrong-password")
    page.wait_for_selector("#message.field-error")
    assert "Неверный логин или пароль" in page.inner_text("#message")
    assert page.input_value("#password") == ""
    page.fill("#password", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/admin/")
    page.wait_for_selector(".stat-card")
    assert page.locator(".stat-card").count() == 4
    assert not page.errors, page.errors


def test_token_not_exposed_to_js_in_browser(admin):
    assert admin.evaluate("() => document.cookie") == ""  # HttpOnly
    assert admin.evaluate("() => Object.keys(localStorage).filter(k => /token/i.test(k))") == []


def test_clubs_crud(admin):
    go(admin, "clubs")
    admin.wait_for_selector("table.data tbody tr")
    assert admin.locator("table.data tbody tr").count() >= 8
    admin.click("text=Добавить кружок")
    admin.fill("#f-name", "Тестовый кружок e2e")
    admin.fill("#f-description", "<b>не разметка</b>")
    admin.select_option("#f-category_id", index=1)
    admin.select_option("#f-leader_id", index=1)
    admin.click("dialog button[type=submit]")
    admin.wait_for_selector("text=Тестовый кружок e2e")
    assert admin.locator("b").count() == 0  # описание не интерпретируется как HTML
    row = admin.locator("tr", has_text="Тестовый кружок e2e")
    row.get_by_role("button", name="Изменить").click()
    admin.fill("#f-name", "Тестовый кружок e2e (2)")
    admin.click("dialog button[type=submit]")
    admin.wait_for_selector("text=Тестовый кружок e2e (2)")
    admin.locator("tr", has_text="Тестовый кружок e2e (2)").get_by_role("button", name="Удалить").click()
    admin.click("dialog button:has-text('Удалить')")
    admin.wait_for_selector("text=Тестовый кружок e2e (2)", state="detached")
    assert not admin.errors, admin.errors


def test_clubs_validation_keeps_dialog_open(admin):
    go(admin, "clubs")
    admin.click("text=Добавить кружок")
    admin.click("dialog button[type=submit]")
    assert admin.locator("dialog[open]").count() == 1
    assert admin.locator("dialog .field-error").count() == 1
    assert admin.locator("#f-name[aria-invalid=true]").count() == 1


def test_session_conflict_is_explained(admin):
    go(admin, "sessions")
    admin.click("text=Добавить занятие")
    # «Программирование для начинающих», Пн 15:00–16:30, ауд. 101 — пересекаемся по аудитории и руководителю
    admin.select_option("#f-club_id", label="Робототехника")
    admin.select_option("#f-room_id", index=1)  # 101
    admin.select_option("#f-weekday", value="1")
    admin.fill("#f-start_time", "15:30")
    admin.fill("#f-end_time", "16:00")
    admin.click("dialog button[type=submit]")
    box = admin.locator("dialog .conflict-box")
    box.wait_for()
    text = box.inner_text()
    assert "Программирование для начинающих" in text and "15:00" in text and "аудитория занята" in text
    assert admin.locator("dialog[open]").count() == 1  # данные не потеряны


def test_cancel_checks_weekday_then_creates_and_removes(admin):
    go(admin, "exceptions")
    admin.click("button:has-text('Отменить занятие')")
    admin.select_option("#f-session_id", label="Рисунок и живопись — Вт 14:00–16:00, 205")
    admin.fill("#f-original_date", "2027-01-04")  # понедельник, а занятие по вторникам
    admin.fill("#f-comment", "e2e-отмена")
    admin.click("dialog button[type=submit]")
    admin.wait_for_selector("dialog .field-error")
    assert "выбери подходящую дату" in admin.inner_text("dialog .form-feedback")
    admin.fill("#f-original_date", "2027-01-05")
    admin.click("dialog button[type=submit]")
    row = admin.locator("tr", has_text="e2e-отмена")
    row.wait_for()
    assert "Отмена" in row.inner_text()
    row.get_by_role("button", name="Удалить").click()
    admin.click("dialog button:has-text('Удалить запись')")
    row.wait_for(state="detached")


def test_reference_in_use_cannot_be_deleted_and_new_can(admin):
    go(admin, "reference/categories")
    admin.locator("tr", has_text="Наука").get_by_role("button", name="Удалить").click()
    admin.wait_for_selector("text=Удалить нельзя")
    admin.click("dialog button:has-text('Понятно')")
    admin.click("text=Добавить направление")
    admin.fill("#f-name", "Временное")
    admin.click("dialog button[type=submit]")
    admin.wait_for_selector("tr:has-text('Временное')")
    admin.locator("tr", has_text="Временное").get_by_role("button", name="Удалить").click()
    admin.click("dialog button:has-text('Удалить')")
    admin.wait_for_selector("tr:has-text('Временное')", state="detached")


def test_password_change_wrong_current_and_mismatch(admin):
    go(admin, "account")
    admin.click("text=Сменить пароль")
    admin.fill("#f-current_password", "not-my-password")
    admin.fill("#f-new_password", "Another-pass-123")
    admin.fill("#f-repeat", "Another-pass-124")
    admin.click("dialog button[type=submit]")
    assert "не совпадают" in admin.inner_text("dialog .form-feedback")
    admin.fill("#f-repeat", "Another-pass-123")
    admin.click("dialog button[type=submit]")
    admin.wait_for_selector("dialog .field-error:has-text('неверно')")


def test_logout_then_admin_is_closed(admin):
    admin.click("button[aria-label=Выйти]")
    admin.wait_for_url("**/admin/login.html")
    admin.goto("/admin/")
    admin.wait_for_url("**/admin/login.html")


def test_expired_session_redirects_from_inside_app(admin):
    admin.context.clear_cookies()
    admin.evaluate("() => { location.hash = '#/clubs'; }")
    admin.wait_for_url("**/admin/login.html?next=*")


def test_expired_session_returns_to_same_section_after_login(admin):
    admin.context.clear_cookies()
    admin.evaluate("() => { location.hash = '#/sessions'; }")
    admin.wait_for_url("**/admin/login.html?next=*")
    admin.fill("#login", "admin")
    admin.fill("#password", ADMIN_PASSWORD)
    admin.click("button[type=submit]")
    admin.wait_for_url("**/admin/#/sessions")
    admin.wait_for_selector("#view-title")
    assert admin.inner_text("#view-title")


def test_expired_access_is_silently_refreshed_via_cookie(admin):
    admin.context.clear_cookies(name="admin_session")  # как будто access-токен истёк, refresh-cookie жива
    names_before = {c["name"] for c in admin.context.cookies()}
    assert "admin_refresh" in names_before and "admin_session" not in names_before
    responses = []
    admin.on("response", lambda r: responses.append((r.status, r.url.split("/api/")[-1])) if "/api/admin" in r.url else None)
    admin.reload()
    admin.wait_for_load_state("networkidle")
    assert "/login.html" not in admin.url, (admin.url, responses, admin.context.cookies())
    admin.wait_for_selector("#view-title")
    assert "admin_session" in {c["name"] for c in admin.context.cookies()}  # access выдан заново ротацией
    assert not admin.errors, admin.errors


def test_expired_access_inside_running_app_is_refreshed_without_leaving(admin):
    admin.context.clear_cookies(name="admin_session")
    responses = []
    admin.on("response", lambda r: responses.append((r.status, r.url.split("/api/")[-1])) if "/api/admin" in r.url else None)
    go(admin, "clubs")
    admin.wait_for_selector("#admin-main:not([aria-busy])")
    assert "/login.html" not in admin.url, (admin.url, responses)
    assert (200, "admin/refresh") in responses, responses
    assert admin.locator("#admin-main .error-state").count() == 0, responses


def test_login_next_param_ignores_external_and_script_values(new_page):
    page = new_page()
    page.goto("/admin/login.html?next=" + "https%3A%2F%2Fevil.example%2F")
    page.fill("#login", "admin")
    page.fill("#password", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/admin/")
    assert page.url.endswith("/admin/")


def test_mobile_layout_bottom_nav_no_overflow(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True)
    do_login(page)
    page.wait_for_url("**/admin/")
    page.wait_for_selector("#view-title")
    assert page.locator(".bottom-nav").is_visible()
    assert not page.locator(".admin-nav").is_visible()
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    go(page, "clubs")
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert not page.errors, page.errors


def test_dashboard_has_no_stray_text_nodes(admin):
    go(admin, "")
    text = admin.inner_text("#admin-main")
    assert "false" not in text and "null" not in text and "undefined" not in text


def test_360px_no_horizontal_overflow_admin_and_public(new_page):
    """ADM-05 / PUB-04: самый узкий распространённый экран — 360 px."""
    page = new_page(360, 740, is_mobile=True, has_touch=True)
    overflow = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    for path in ("/", "/clubs.html", "/club.html?id=1", "/install"):
        page.goto(path)
        page.wait_for_load_state("load")
        page.wait_for_timeout(300)
        assert page.evaluate(overflow) <= 0, f"горизонтальный скролл на {path}"
    do_login(page)
    page.wait_for_url("**/admin/")
    page.wait_for_selector("#view-title")
    for route in ("", "clubs", "sessions", "exceptions", "reference/rooms", "account"):
        go(page, route)
        assert page.evaluate(overflow) <= 0, f"горизонтальный скролл в админке #/{route}"
    assert not page.errors, page.errors


def test_settings_dark_theme_on_admin_persists(admin):
    admin.click("[data-settings-button]")
    admin.check("input[name=theme][value=dark]", force=True)
    assert admin.evaluate("() => document.documentElement.dataset.theme") == "dark"
    admin.reload()
    admin.wait_for_selector("#view-title")
    assert admin.evaluate("() => document.documentElement.dataset.theme") == "dark"
    bg = admin.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert bg == "rgb(17, 20, 18)"
    assert not admin.errors, admin.errors
