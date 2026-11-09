from pathlib import Path

from playwright.sync_api import expect


def test_live_now_next15_and_other_day(new_page):
    page = new_page(390, 844)
    page.clock.set_fixed_time("2026-11-09T15:30:00+03:00")
    page.goto("/?day=2026-11-09")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors
    notice = page.get_by_role("button", name="Понятно", exact=True)
    if notice.is_visible():
        notice.click()
    expect(page.locator('[data-live-kind="now"] .event-live').first).to_contain_text("Сейчас")
    expect(page.locator('[data-live-kind="now"] [role=progressbar]').first).to_have_attribute("aria-valuenow", "33")
    page.goto("/?day=2026-11-09")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors
    notice = page.get_by_role("button", name="Понятно", exact=True)
    if notice.is_visible():
        notice.click()
    page.clock.set_fixed_time("2026-11-09T14:45:00+03:00")
    page.reload()
    expect(page.locator('[data-live-kind="soon"] .event-live').first).to_contain_text("Через 15 мин")
    page.goto("/?day=2026-11-10")
    expect(page.locator(".event-name").first).to_be_visible()
    expect(page.locator(".event-live:visible")).to_have_count(0)
    assert not page.errors, page.errors


def test_event_favorites_persist_and_link_to_filter(new_page):
    page = new_page(390, 844)
    page.goto("/?day=2026-11-09")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors
    notice = page.get_by_role("button", name="Понятно", exact=True)
    if notice.is_visible():
        notice.click()
    page.locator(".calendar-event").first.click()
    leaders = page.locator('[data-favorite^="leaders:"]')
    rooms = page.locator('[data-favorite^="rooms:"]')
    leaders.first.click()
    rooms.first.click()
    expect(leaders.first).to_have_attribute("aria-pressed", "true")
    expect(rooms.first).to_have_attribute("aria-pressed", "true")
    page.locator("#close-event").click()
    page.get_by_role("button", name="Настройки", exact=True).click()
    expect(page.locator("[data-favorites-section] a")).to_have_count(2)
    page.locator('[data-favorites-section] a[href*="leader_id"]').click()
    expect(page.locator("#leader")).not_to_have_value("")
    assert page.locator("#leader option:checked").inner_text().startswith("★")
    page.locator(".calendar-event").first.click()
    expect(page.locator('[data-favorite^="leaders:"]').first).to_have_attribute("aria-pressed", "true")
    assert not page.errors, page.errors


def test_one_occurrence_calendar_download(new_page):
    page = new_page(390, 844)
    page.goto("/?day=2026-11-09")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors
    notice = page.get_by_role("button", name="Понятно", exact=True)
    if notice.is_visible():
        notice.click()
    page.locator(".calendar-event").first.click()
    with page.expect_download() as download:
        page.get_by_role("button", name="В календарь телефона", exact=True).click()
    text = Path(download.value.path()).read_text(encoding="utf-8").replace("\n ", "")
    assert text.count("BEGIN:VEVENT") == 1
    assert "DTSTART:20261109T120000Z" in text
    assert "Программирование для начинающих" in text
    assert not page.errors, page.errors


def test_notification_form_saves_arbitrary_minutes_and_quiet_hours(new_page):
    page = new_page(390, 844)
    page.goto("/?day=2026-11-09")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors
    notice = page.get_by_role("button", name="Понятно", exact=True)
    if notice.is_visible():
        notice.click()
    page.evaluate(
        """async()=>{const src=Array.from(document.scripts).find(s=>new URL(s.src||location.href).pathname.endsWith('/js/schedule.js')).src;const m=await import(src.replace('schedule.js','schedule-notification-form.js'));m.mountScheduleNotificationForm(document.body,{load:async()=>({reminder_minutes:0,quiet_enabled:false,quiet_start:'22:00',quiet_end:'08:00',digest_enabled:false,digest_time:'08:00'}),save:async v=>{window.__saved=v}})}"""
    )
    page.locator("[name=reminder_minutes]").fill("17")
    page.locator("[name=quiet_enabled]").check()
    page.locator("[name=digest_enabled]").check()
    page.get_by_role("button", name="Сохранить расписание уведомлений").click()
    expect(page.locator(".personal-notification-form [role=status]")).to_have_text("Настройки уведомлений сохранены")
    saved = page.evaluate("window.__saved")
    assert saved["reminder_minutes"] == 17 and saved["quiet_enabled"] and saved["digest_enabled"]
    page.locator("[name=quiet_end]").fill("22:00")
    page.get_by_role("button", name="Сохранить расписание уведомлений").click()
    expect(page.locator(".personal-notification-form [role=status]")).to_contain_text("должны отличаться")
    assert not page.errors, page.errors
