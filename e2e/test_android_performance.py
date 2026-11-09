"""Android-only ribbon path: same shared date logic, compositor-only movement."""
from pathlib import Path

from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[1]


def test_native_ribbon_cancels_overlap_and_keeps_layout(new_page):
    page = new_page(390, 844, is_mobile=True, has_touch=True)
    page.route('**/css/native-performance.css', lambda route: route.fulfill(path=str(ROOT / 'android/shim/native-performance.css'), content_type='text/css'))
    page.add_init_script("window.ItcPerformance = { enabled: true, beginMotion() {} }")
    page.goto('/?week=2026-11-09&day=2026-11-10')
    page.evaluate("document.documentElement.dataset.nativePerf = 'true'")
    page.add_style_tag(url='/css/native-performance.css')
    expect(page.locator('#content')).to_have_attribute('aria-busy', 'false')
    rail = page.locator('#day-buttons')
    expect(rail).to_have_class('glass-tabs ribbon-transform')
    expect(rail.locator('.ribbon-track')).to_have_count(1)
    page.evaluate("""() => {
        const rail = document.querySelector('#day-buttons');
        window.__scrollCalls = 0;
        rail.scrollTo = () => { window.__scrollCalls++; throw Error('ribbon must not scroll'); };
        rail.scrollIntoView = rail.scrollTo;
    }""")
    for day in ('2026-11-11', '2026-11-12', '2026-11-10'):
        # Programmatic activation allows overlapping animation; the selected tab is otherwise moving under touch.
        rail.locator(f'[data-day-date="{day}"]').evaluate('el => el.click()')
        expect(rail.locator('[aria-pressed="true"]')).to_have_attribute('data-day-date', day)
        assert rail.evaluate("el => el.querySelector('.ribbon-track').getAnimations().length") <= 1
    track = rail.locator('.ribbon-track')
    track.evaluate('el => Promise.allSettled(el.getAnimations().map(a => a.finished))')
    active = rail.locator('[aria-pressed="true"]').bounding_box()
    bounds = rail.bounding_box()
    assert abs(active['x'] - bounds['x'] - 2 * bounds['width'] / 6) < 1
    assert page.evaluate('window.__scrollCalls') == 0
    assert rail.evaluate('el => el.scrollLeft') == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('[data-settings-button]').click()
    page.get_by_text('По неделям', exact=True).click()
    page.get_by_role('button', name='Закрыть настройки').click()
    expect(rail.locator('[data-day-date]')).to_have_count(6)
    assert not page.errors, page.errors
