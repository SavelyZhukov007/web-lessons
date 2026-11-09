from pathlib import Path

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("width,scheme", [(390, "light"), (390, "dark"), (320, "light"), (320, "dark")])
def test_native_ribbon_real_accessible_names_and_touch_targets(new_page, width, scheme):
    page = new_page(width, 844, is_mobile=True, has_touch=True, color_scheme=scheme)
    page.route(
        "**/css/native-performance.css",
        lambda route: route.fulfill(path=str(ROOT / "android/shim/native-performance.css"), content_type="text/css"),
    )
    page.add_init_script("window.ItcPerformance={enabled:true,beginMotion(){}}")
    page.goto("/?week=2026-11-09&day=2026-11-10")
    page.evaluate("document.documentElement.dataset.nativePerf='true';document.documentElement.classList.add('platform-android')")
    page.evaluate("import('/js/ui.js').then(m=>m.installRipple())")
    page.add_style_tag(url="/css/native-performance.css")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    rail = page.locator("#day-buttons")
    expect(rail.locator(".ribbon-track")).to_have_attribute("aria-hidden", "true")
    expect(rail.get_by_role("button")).to_have_count(6)
    for button in rail.get_by_role("button").all():
        assert button.get_attribute("aria-label") and "ноября" in button.get_attribute("aria-label")
        rect = button.bounding_box()
        assert rect["width"] >= 44 and rect["height"] >= 44
    active = rail.get_by_role("button", pressed=True)
    expect(active).to_have_attribute("data-day-date", "2026-11-10")
    height = rail.bounding_box()["height"]
    rail.locator('[data-day-date="2026-11-11"]').tap()
    expect(rail.get_by_role("button", pressed=True)).to_have_attribute("data-day-date", "2026-11-11")
    assert rail.bounding_box()["height"] == height
    rail.locator('[data-day-date="2026-11-10"]').tap()
    expect(rail.get_by_role("button", pressed=True)).to_have_attribute("data-day-date", "2026-11-10")
    active.focus()
    expect(active).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(rail.get_by_role("button", pressed=True)).to_have_attribute("data-day-date", "2026-11-11")
    assert "выбрано" in rail.aria_snapshot()
    page.locator("#today").click()
    expect(page.locator("#today")).to_have_attribute("aria-pressed", "true")
    contrast = page.evaluate(r"""() => {
      const s=getComputedStyle(document.querySelector('#today'));
      const rgb=v=>v.match(/[\d.]+/g).slice(0,3).map(Number);
      const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
      const a=luminance(rgb(s.color)),b=luminance(rgb(s.backgroundColor));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    }""")
    assert contrast >= 4.5
    page.evaluate("ClubsTheme.set({dayNavigation:'week'})")
    rail.get_by_role("button", pressed=True).focus()
    page.keyboard.press("ArrowRight")
    expect(rail.get_by_role("button", pressed=True)).to_have_attribute("data-day-date", "2026-11-10")
    page.keyboard.press("ArrowRight")
    expect(rail.get_by_role("button", pressed=True)).to_have_attribute("data-day-date", "2026-11-11")
    expect(rail.get_by_role("button", pressed=True)).to_be_focused()
    page.evaluate("document.documentElement.dataset.nativeScreenReader='true'")
    assert page.evaluate("import('/js/motion-preferences.js').then(m=>m.prefersReducedMotion())")
    assert not page.errors, page.errors


def test_tour_link_and_telemetry_opt_in_no_raw_query(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True)
    batches = []
    page.route("**/api/app/usage", lambda r: (batches.append(r.request.post_data_json), r.fulfill(status=202, json={"accepted": 1})))
    page.goto("/")
    expect(page.locator("#content")).to_have_attribute("aria-busy", "false")
    assert not batches
    page.locator("[data-settings-button]").click()
    tour = page.get_by_role("link", name="3D-тур КИПФИН", exact=False)
    expect(tour).to_have_attribute("href", "https://tour.panoee.net/65e08e217a73f2feff4db099/65e08e717a73f212cb4db0ac")
    toggle = page.get_by_role("switch", name="Анонимная статистика и технические ошибки", exact=True)
    expect(toggle).to_have_attribute("aria-checked", "false")
    rect = toggle.bounding_box()
    assert rect["width"] >= 44 and rect["height"] >= 44
    toggle.click()
    page.get_by_role("button", name="Закрыть настройки", exact=True).click()
    page.locator("#search").fill("private-secret-no-results")
    expect(page.locator("#search-status")).to_contain_text("ничего")
    page.locator("#search-exit").click()
    page.evaluate(
        "window.dispatchEvent(new ErrorEvent('error',{filename:'https://example.test/schedule.js?token=private-secret',lineno:12,error:new TypeError('private-secret')}))"
    )
    page.evaluate("window.KipUsage.flush()")
    assert batches
    import json

    encoded = json.dumps(batches)
    assert "private-secret" not in encoded and "token" not in encoded and "install_id" not in encoded
    metrics = [e["metric"] for b in batches for e in b["events"]]
    assert "search_results" in metrics and "search_abandon" in metrics
    assert batches[0]["errors"][0]["code"] == "TypeError"
    page.locator("[data-settings-button]").click()
    page.get_by_role("switch", name="Анонимная статистика и технические ошибки", exact=True).click()
    page.evaluate("window.KipUsage.emit('search_open');window.KipUsage.flush()")
    assert len(batches) == 1
    assert not page.errors, page.errors
