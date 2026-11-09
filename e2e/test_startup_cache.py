"""Startup rendering must not wait for a slow refresh, nor parse optional panels."""
import time

from playwright.sync_api import expect


def test_persistent_week_is_visible_while_revalidation_is_still_pending(new_page):
    page = new_page(390, 844, service_workers="block")
    page.goto("/?day=2026-11-09")
    expect(page.locator(".calendar-event").first).to_be_visible()
    page.wait_for_function("""() => new Promise(resolve => {
      const r = indexedDB.open('kipclub.schedule.v1', 1);
      r.onsuccess = () => { const db=r.result; const q=db.transaction('weeks').objectStore('weeks').getAll();
        q.onsuccess=()=>{resolve(q.result.some(row=>row.week==='2026-11-09' && row.events.length));db.close();}; };
      r.onerror=()=>resolve(false);
    })""")
    pending = []
    page.route("**/api/schedule?**", lambda route: pending.append(route))
    started = time.perf_counter()
    page.reload(wait_until="commit")
    expect(page.locator(".calendar-event").first).to_be_visible(timeout=2500)
    assert pending, "The network refresh should still be in flight"
    assert time.perf_counter() - started < 2.5
    assert not page.locator(".schedule-state[role=alert]").count()
    for route in pending:
        route.abort("internetdisconnected")
    assert not page.errors, page.errors


def test_settings_and_search_ui_are_lazy_but_first_interaction_works(new_page):
    page = new_page(390, 844, service_workers="block")
    page.goto("/?day=2026-11-10")
    expect(page.locator(".calendar-event").first).to_be_visible()
    resources = page.evaluate("performance.getEntriesByType('resource').map(r=>r.name)")
    assert not any('/settings-panel.js' in path or '/schedule-search.js' in path or '/print.js' in path or '/js/admin/' in path for path in resources)
    query = page.locator('.event-name').first.inner_text()
    page.get_by_role('button', name='Настройки', exact=True).click()
    expect(page.locator('#settings-dialog')).to_be_visible()
    page.get_by_role('button', name='Закрыть настройки', exact=True).click()
    page.locator('#search').fill(query)
    expect(page.locator('#search-status')).to_contain_text('найдено')
    assert not page.errors, page.errors


def test_existing_scroll_lock_restores_position_without_a_jump(new_page):
    page = new_page(390, 640, service_workers="block", is_mobile=True, has_touch=True)
    page.goto('/?day=2026-11-10')
    expect(page.locator('.calendar-event').first).to_be_visible()
    page.evaluate('window.scrollTo(0, 180)')
    before = page.evaluate('scrollY')
    assert before > 0
    page.evaluate('window.ClubsSettings.open()')
    expect(page.locator('#settings-dialog')).to_be_visible()
    page.get_by_role('button', name='Закрыть настройки', exact=True).click()
    page.wait_for_function('(before) => Math.abs(scrollY-before)<2', arg=before)
    assert not page.errors, page.errors
