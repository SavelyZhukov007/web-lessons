"""Release notes and shareable schedule links on a narrow viewport."""
from playwright.sync_api import expect


def test_release_notes_open_once_and_from_announcement(new_page):
    page = new_page(390, 844, show_release=True)
    page.goto("/")
    page.get_by_role("heading", name="Что нового в v1.9.015").wait_for()
    page.get_by_role("button", name="Понятно", exact=True).click()
    page.reload()
    page.wait_for_load_state("networkidle")
    assert not page.locator(".release-sheet").is_visible()
    page.get_by_role("button", name="Настройки", exact=True).click()
    page.get_by_role("button", name="Что нового", exact=True).click()
    page.get_by_role("heading", name="Что нового в v1.9.015").wait_for()
    page.get_by_role("button", name="Понятно", exact=True).click()
    page.goto("/?update=1&release=v1.9.015")
    page.get_by_role("heading", name="Что нового в v1.9.015").wait_for()
    assert not page.errors


def test_share_selected_day_reload_and_back(new_page):
    page = new_page(320, 740)
    page.goto("/?week=2026-11-09&day=2026-11-10")
    assert page.locator("#selected-day-label").inner_text() == "Вторник, 10 ноября"
    page.locator("#search").fill("нет такого кружка")
    expect(page.locator("#search-status")).to_have_text("вторник, 10 ноября · ничего не нашлось")
    page.get_by_role("button", name="Закрыть поиск").click()
    page.locator('[data-day-date="2026-11-11"]').click()
    page.wait_for_url("**/*day=2026-11-11")
    page.go_back()
    assert page.locator("#selected-day-label").inner_text() == "Вторник, 10 ноября"
    page.reload()
    assert page.locator("#selected-day-label").inner_text() == "Вторник, 10 ноября"
    page.goto("/?week=2026-11-09&day=2026-11-31")
    assert page.locator("#selected-day-label").inner_text() == "Понедельник, 9 ноября"
    assert not page.errors
