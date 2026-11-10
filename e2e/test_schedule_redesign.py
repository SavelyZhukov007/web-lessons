"""The date ribbon, schedule search and settings gestures use the real public UI."""
from urllib.parse import parse_qs, urlsplit

import pytest
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
    page.locator("#content").evaluate("(el) => { el.style.minHeight = '1500px'; }")
    page.evaluate("window.scrollTo(0, 220)")
    previous = page.locator("#schedule-filters").bounding_box()["y"]
    page.evaluate("window.ClubsSettings.open()")
    sheet = page.locator("#settings-dialog")
    expect(page.locator("html")).to_have_attribute("data-modal-scroll-lock", "")
    page.evaluate("window.scrollTo(0, 800)")
    assert abs(page.locator("#schedule-filters").bounding_box()["y"] - previous) <= 1
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
    assert page.evaluate("scrollY") == 220
    page.get_by_role("button", name="Настройки", exact=True).click()
    page.get_by_role("button", name="Закрыть настройки").click()
    expect(sheet).to_be_hidden()
    assert not page.errors, page.errors


def test_schedule_preferences_keep_day_and_change_card_density(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True, color_scheme="light")
    page.goto("/?week=2026-11-09&day=2026-11-10")
    page.locator(".storage-notice button").click()
    active = page.locator('#day-buttons [aria-pressed="true"]')
    expect(active.locator("strong")).to_have_css("color", "rgb(255, 255, 255)")
    expect(active.locator(".ribbon-weekday")).to_have_css("color", "rgb(255, 255, 255)")
    card = page.locator("#content button[data-event-id]").first
    card.wait_for()
    page.locator(".schedule-skeleton").wait_for(state="detached")
    original_height = card.bounding_box()["height"]
    page.get_by_role("button", name="Настройки", exact=True).click()
    sheet = page.locator("#settings-dialog")
    sheet.get_by_text("По неделям", exact=True).click()
    sheet.get_by_text("Карточки занятий", exact=True).click()
    sheet.get_by_text("Компактный список", exact=True).click()
    sheet.get_by_text("Аудитории", exact=True).click()
    sheet.get_by_text("Эффекты и доступность", exact=True).click()
    sheet.get_by_text("Непрозрачные панели", exact=True).click()
    page.get_by_role("button", name="Закрыть настройки").click()
    expect(page.locator("#day-buttons [data-day-date]")).to_have_count(6)
    expect(active).to_have_attribute("data-day-date", "2026-11-10")
    expect(card.locator(".event-room")).to_be_hidden()
    assert card.bounding_box()["height"] < original_height
    expect(page.locator(".mobile-days")).to_have_css("backdrop-filter", "none")
    rail = page.locator("#day-buttons").bounding_box()
    middle = rail["y"] + rail["height"] / 2
    cdp = page.context.new_cdp_session(page.page)
    _drag(cdp, (300, middle), (65, middle))
    expect(active).to_have_attribute("data-day-date", "2026-11-17")
    _drag(cdp, (65, middle), (300, middle))
    expect(active).to_have_attribute("data-day-date", "2026-11-10")
    page.reload()
    expect(page.locator("#day-buttons [data-day-date]")).to_have_count(6)
    expect(card.locator(".event-room")).to_be_hidden()
    card.click()
    expect(page.locator("#event-dialog").get_by_text("Аудитория", exact=True)).to_be_visible()
    assert not page.errors, page.errors


def test_dark_desktop_segment_uses_a_single_contrasting_pill(new_page):
    page = new_page(1366, 900, color_scheme="dark")
    page.goto("/?week=2026-11-09&day=2026-11-10")
    page.locator("#view-list").click()
    choice = page.locator("#view-list")
    expect(choice).to_have_css("background-color", "rgba(0, 0, 0, 0)")
    pill = page.locator(".desktop-view .glass-indicator")
    expect(pill).to_have_class("glass-indicator is-visible")
    contrast = choice.evaluate("""button => {
        const hex = color => '#' + color.match(/\\d+/g).slice(0, 3).map(v => Number(v).toString(16).padStart(2, '0')).join('');
        const color = el => getComputedStyle(el).color;
        const fill = getComputedStyle(button.parentElement.querySelector('.glass-indicator')).backgroundColor;
        return ClubsTheme.contrast(hex(color(button)), hex(fill));
    }""")
    assert contrast >= 4.5
    page.locator(".storage-notice button").click()
    pill.evaluate("el => Promise.allSettled(el.getAnimations().map(a => a.finished))")
    shot(page, "kipclub-desktop-list-dark.png")
    assert not page.errors, page.errors


@pytest.mark.parametrize(("width", "scheme"), [(320, "light"), (1366, "dark")])
def test_moved_slot_opens_and_shares_the_actual_event(new_page, width, scheme):
    page = new_page(width, 844, is_mobile=width < 600, has_touch=width < 600, color_scheme=scheme, reduced_motion="reduce")
    page.add_init_script("Object.defineProperty(navigator, 'share', { value: async payload => { window.shared = payload; } })")
    page.goto("/?day=2026-10-23")
    page.locator(".storage-notice button").click()
    if width >= 1000:
        page.locator("#view-list").click()
    old_slot = page.locator(".schedule-list .itc-ghost")
    action = old_slot.get_by_role("button", name="Актуальное время", exact=False)
    expect(action).to_be_visible()
    title = old_slot.locator(".event-name").bounding_box()
    link_box = action.bounding_box()
    row = old_slot.bounding_box()
    assert abs(link_box["x"] - title["x"]) <= 1
    assert link_box["width"] >= 140
    assert link_box["x"] + link_box["width"] <= row["x"] + row["width"] + 1
    old_slot.scroll_into_view_if_needed()
    shot(page, f"kipclub-moved-slot-{'desktop' if width >= 1000 else 'mobile'}-{scheme}.png")
    action.click()
    target = page.locator(".calendar-event.itc-flash")
    expect(target).to_be_focused()
    link = page.url
    query = parse_qs(urlsplit(link).query)
    assert query["day"] == ["2026-10-24"]
    event_id = target.get_attribute("data-event-id")
    assert query["event"] == [event_id]
    page.reload()
    if width < 1000:
        expect(target).to_be_focused()
    page.locator(f'.calendar-event[data-event-id="{event_id}"]').click()
    page.get_by_role("button", name="Поделиться занятием").click()
    shared = urlsplit(page.evaluate("window.shared.url"))
    expected = urlsplit(link)
    assert (shared.netloc, shared.path, parse_qs(shared.query)) == (expected.netloc, expected.path, parse_qs(expected.query))
    assert not page.errors, page.errors


def test_moved_slot_inside_parallel_group_jumps_to_actual_event(new_page):
    page = new_page(1366, 900, reduced_motion="reduce")

    def add_overlapping_slot(route):
        response = route.fetch()
        events = response.json()
        moved = next(e for e in events if e["status"] == "moved" and e["original_date"] == "2026-10-23")
        events.append({
            **moved, "event_id": "parallel-test", "club_name": "Параллельное занятие", "status": "scheduled",
            "date": moved["original_date"], "start_time": moved["original_start_time"], "end_time": moved["original_end_time"],
        })
        route.fulfill(response=response, json=events)

    page.route("**/api/schedule?week=2026-10-19", add_overlapping_slot)
    page.goto("/?day=2026-10-23")
    page.locator(".storage-notice button").click()
    page.locator(".parallel-group").filter(has_text="Параллельное занятие").click()
    group = page.get_by_role("dialog", name="Занятия в это время")
    group.get_by_role("button", name="Актуальное время", exact=False).click()
    expect(group).to_be_hidden()
    assert parse_qs(urlsplit(page.url).query)["day"] == ["2026-10-24"]
    expect(page.locator(".calendar-event.itc-flash")).to_be_focused()
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


def test_liquid_glass_header_and_reduced_modes(new_page):
    for width in (390, 320):
        for scheme in ("light", "dark"):
            page = new_page(width, 760, is_mobile=True, has_touch=True, color_scheme=scheme)
            page.goto("/?week=2026-11-09&day=2026-11-10")
            page.locator(".storage-notice button").click()
            page.locator("#content .calendar-event[data-event-id]").first.wait_for()
            layout = page.evaluate("""() => {
                const box = s => document.querySelector(s).getBoundingClientRect();
                const header = document.querySelector('.campus-header');
                const style = getComputedStyle(header);
                const pill = document.querySelector('#day-buttons .glass-indicator');
                const selected = document.querySelector('#day-buttons [aria-pressed="true"]');
                return { gap: box('.search-field').top - box('.campus-header').bottom, border: style.borderBottomWidth,
                         blur: style.backdropFilter, mark: getComputedStyle(document.querySelector('.brand-mark')).filter,
                         bell: !!document.querySelector('.campus-header #itc-notify-open + [data-settings-button]'),
                         rail: box('.mobile-days').bottom - box('#day-buttons').bottom,
                         ink: getComputedStyle(selected).color, pill: pill.classList.contains('is-visible') };
            }""")
            assert layout["gap"] <= 12 and layout["border"] == "0px", layout
            assert layout["blur"] == "none" and layout["mark"] == "none", layout
            assert layout["bell"] and layout["pill"] and layout["rail"] >= 0, layout
            if scheme == "light":
                assert layout["ink"] == "rgb(255, 255, 255)", layout
            # стеклянный материал на кнопках, полосе дней и шторке; блик появляется в точке касания
            assert page.evaluate("getComputedStyle(document.querySelector('#prev-week')).backdropFilter").startswith("blur(")
            page.locator('[data-settings-button]').click()
            sheet = page.locator("#settings-dialog")
            expect(sheet).to_be_visible()
            assert "blur(" in sheet.evaluate("el => getComputedStyle(el).backdropFilter") or sheet.get_attribute("data-glass-backend")
            page.keyboard.press("Escape")
            # «Непрозрачные панели» и «Меньше движения» выключают стекло и пружины
            page.evaluate("window.ClubsTheme.set({ solidGlass: true, reduceMotion: true })")
            assert page.evaluate("getComputedStyle(document.querySelector('#prev-week')).backdropFilter") == "none"
            page.locator('[data-day-date="2026-11-12"]').click()
            assert page.evaluate("document.querySelector('#day-buttons .glass-indicator').getAnimations().length") == 0
            assert not page.errors


@pytest.mark.parametrize("width", [390, 320])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_today_stays_visible_and_uses_the_active_accent(new_page, width, scheme):
    page = new_page(width, 844, is_mobile=True, has_touch=True, color_scheme=scheme)
    page.clock.set_fixed_time("2026-11-09T12:00:00+03:00")
    page.goto("/?week=2026-11-09&day=2026-11-10")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    page.locator(".storage-notice button").click()
    today = page.get_by_role("button", name="Сегодня", exact=True)
    expect(today).to_be_visible()
    expect(today).to_have_attribute("aria-pressed", "false")
    expect(page.locator('#day-buttons [aria-pressed="true"]')).to_have_attribute("data-day-date", "2026-11-10")
    other_box = today.bounding_box()
    actions = page.locator("#schedule-actions").bounding_box()
    assert abs(other_box["x"] + other_box["width"] - actions["x"] - actions["width"]) < 1
    assert other_box["width"] > 90  # растягивается на оставшееся место, не становится иконкой
    shot(page, f"today-web-{width}-{scheme}-other.png")
    today.click()
    expect(today).to_be_visible()
    expect(today).to_be_enabled()
    expect(today).to_have_attribute("aria-pressed", "true")
    expect(page.locator('#day-buttons [aria-pressed="true"]')).to_have_attribute("data-day-date", "2026-11-09")
    primary = today.evaluate("el => { const p = document.createElement('i'); p.style.color = 'var(--primary)'; el.append(p); const c = getComputedStyle(p).color; p.remove(); return c; }")
    expect(today).to_have_css("background-color", primary)
    contrast = today.evaluate("""el => {
        const hex = c => '#' + c.match(/\\d+/g).slice(0, 3).map(v => Number(v).toString(16).padStart(2, '0')).join('');
        const s = getComputedStyle(el);
        return ClubsTheme.contrast(hex(s.color), hex(s.backgroundColor));
    }""")
    assert contrast >= 4.5
    assert today.bounding_box() == other_box  # выделение не меняет раскладку
    today.click()  # повторное нажатие на активную кнопку тоже разрешено
    expect(today).to_have_attribute("aria-pressed", "true")
    shot(page, f"today-web-{width}-{scheme}-selected.png")
    page.locator('[data-day-date="2026-11-10"]').click()
    expect(today).to_be_visible()
    expect(today).to_have_attribute("aria-pressed", "false")
    page.reload()
    expect(today).to_have_attribute("aria-pressed", "false")
    today.click()
    expect(today).to_have_attribute("aria-pressed", "true")
    page.reload()
    expect(today).to_be_visible()
    expect(today).to_have_attribute("aria-pressed", "true")
    assert not page.errors, page.errors
