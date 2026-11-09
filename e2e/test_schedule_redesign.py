"""The date ribbon, schedule search and settings gestures use the real public UI."""
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from .conftest import do_login
from .test_frontend_workflows import shot


def _drag(cdp, start, end):
    def touch(kind, points):
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    touch("touchStart", [{"x": start[0], "y": start[1]}])
    for i in range(1, 13):
        touch("touchMove", [{"x": start[0] + (end[0] - start[0]) * i / 12, "y": start[1] + (end[1] - start[1]) * i / 12}])
    touch("touchEnd", [])


def test_search_keeps_day_scope_and_understands_layout(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True)
    page.goto("/?week=2026-11-09&day=2026-11-10")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    page.locator(".storage-notice button").click()
    page.locator("#content .calendar-event[data-event-id]").first.wait_for()
    page.locator(".schedule-skeleton").wait_for(state="detached")
    shot(page, "kipclub-schedule-390.png")
    query = page.locator("#search")
    for value in ("робототехника", "hj,jnjnt[ybrf", "robototekhnika", "робототехнка"):
        query.fill(value)
        expect(page.locator(".search-result-name mark")).to_have_text("Робототехника")
        expect(query).to_have_value(value)
    page.locator("#schedule-overview").wait_for(state="hidden")
    shot(page, "kipclub-search-390.png")
    assert page.locator("#schedule-overview").evaluate("(overview) => overview.inert")
    expect(page.get_by_role("link", name="Все кружки")).to_be_visible()
    query.press("Enter")
    page.get_by_role("button", name="Закрыть поиск").click()
    page.locator('[data-day-date="2026-11-14"]').click()
    query.fill("робототехника")
    expect(page.locator("#search-status")).to_have_text("суббота, 14 ноября · ничего не нашлось")
    page.get_by_role("button", name="Вся неделя").click()
    expect(page.locator(".search-result-name").first).to_have_text("Робототехника")
    page.locator(".search-result").first.click()
    expect(page.locator('[data-day-date="2026-11-10"]')).to_have_attribute("aria-pressed", "true")
    assert "event=" in page.url
    expect(page.locator(".calendar-event.itc-flash")).to_be_focused()
    query.focus()
    expect(page.get_by_role("heading", name="Недавние запросы")).to_be_visible()
    page.get_by_role("button", name="Очистить").click()
    expect(page.get_by_role("heading", name="Недавние запросы")).to_have_count(0)
    assert not page.errors, page.errors


def test_ribbon_swipe_crosses_sunday_and_keeps_the_header(new_page):
    page = new_page(320, 740, is_mobile=True, has_touch=True)
    page.goto("/?week=2026-11-09&day=2026-11-14")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    box = page.locator("#day-buttons").bounding_box()
    position = page.locator('[aria-pressed="true"][data-day-date]').bounding_box()
    assert abs(position["x"] - box["x"] - 2 * box["width"] / 6) < 3
    week = page.locator(".week-navigation").bounding_box()
    calendar = page.locator(".date-picker").bounding_box()
    assert calendar["x"] >= week["x"] + week["width"] and calendar["width"] == 44
    header = page.locator("#schedule-filters").bounding_box()
    cdp = page.context.new_cdp_session(page.page)
    y = page.locator("#content").bounding_box()["y"] + 80
    _drag(cdp, (270, y), (55, y + 5))
    expect(page.locator('[data-day-date="2026-11-16"]')).to_have_attribute("aria-pressed", "true")
    _drag(cdp, (270, y), (55, y + 5))
    expect(page.locator('[data-day-date="2026-11-17"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    assert page.locator("#schedule-filters").bounding_box() == header
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors, page.errors


def test_settings_dismiss_requires_a_new_drag_at_the_top(new_page):
    page = new_page(390, 620, is_mobile=True, has_touch=True)
    page.goto("/")
    page.get_by_role("button", name="Настройки", exact=True).click()
    sheet = page.locator("#settings-dialog")
    body = sheet.locator(".sheet-body")
    top = body.evaluate("(el) => { el.scrollTop = el.scrollHeight; return el.scrollTop; }")
    assert top > 0
    bounds = body.bounding_box()
    y = bounds["y"] + 10
    cdp = page.context.new_cdp_session(page.page)
    _drag(cdp, (bounds["x"] + 18, y), (bounds["x"] + 18, y + min(160, bounds["height"] - 20)))
    expect(sheet).to_be_visible()
    assert body.evaluate("(el) => el.scrollTop") < top
    body.evaluate("(el) => { el.scrollTop = 0; }")
    head = sheet.locator(".sheet-head").bounding_box()
    x, y = head["x"] + head["width"] / 2, head["y"] + head["height"] / 2
    _drag(cdp, (x, y), (x, y + 165))
    expect(sheet).to_be_hidden()
    page.get_by_role("button", name="Настройки", exact=True).click()
    page.get_by_role("button", name="Закрыть настройки").click()
    expect(sheet).to_be_hidden()
    assert not page.errors, page.errors


def test_moved_slot_opens_and_shares_the_actual_event(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True, reduced_motion="reduce")
    page.add_init_script("Object.defineProperty(navigator, 'share', { value: async payload => { window.shared = payload; } })")
    page.goto("/?day=2026-10-23")
    page.locator(".storage-notice button").click()
    page.locator(".itc-ghost-link").click()
    target = page.locator(".calendar-event.itc-flash")
    expect(target).to_be_focused()
    expect(page.locator('[data-day-date="2026-10-24"]')).to_have_attribute("aria-pressed", "true")
    link = page.url
    assert "event=" in link
    page.reload()
    expect(target).to_be_focused()
    target.click()
    page.get_by_role("button", name="Поделиться занятием").click()
    shared = urlsplit(page.evaluate("window.shared.url"))
    expected = urlsplit(link)
    assert (shared.netloc, shared.path, parse_qs(shared.query)) == (expected.netloc, expected.path, parse_qs(expected.query))
    assert not page.errors, page.errors


def test_glass_broadcast_controls_keep_draft_and_show_future_count(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True, color_scheme="dark")
    do_login(page)
    page.wait_for_url("**/admin/")
    page.route("**/api/admin/exceptions", lambda route: route.fulfill(json=[
        {"original_date": "2099-11-08", "new_date": None},
        {"original_date": "2020-11-08", "new_date": None},
    ]))
    nav = page.locator(".bottom-nav")
    expect(nav).to_be_visible()
    notice = page.locator(".storage-notice")
    expect(notice).to_be_visible()
    assert notice.bounding_box()["y"] + notice.bounding_box()["height"] < nav.bounding_box()["y"]
    nav.locator('[data-route="broadcasts"]').click()
    notice.locator("button").click()
    title = page.locator("#bc-title")
    title.fill("Проверка стекла")
    audience = page.get_by_role("radiogroup", name="Кому отправить")
    audience.get_by_role("radio", name="Кружкам").check()
    expect(audience.locator(".glass-indicator")).to_have_class("glass-indicator is-visible")
    expect(nav).to_have_attribute("data-glass-backend", "css-svg")
    expect(nav.locator('[data-route="exceptions"] .admin-change-count')).to_have_text("1")
    expect(title).to_have_value("Проверка стекла")
    expect(nav.locator('[data-route="broadcasts"]')).to_have_attribute("aria-current", "page")
    audience.locator(".glass-indicator").evaluate("(el) => Promise.allSettled(el.getAnimations().map(animation => animation.finished))")
    shot(page, "kipclub-admin-glass-390.png")
    assert not page.errors, page.errors
