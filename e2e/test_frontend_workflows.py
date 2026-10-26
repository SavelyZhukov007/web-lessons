"""Регрессии пользовательских сценариев задач 7–11. Только временная БД стенда."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect


def shot(page, name):
    if os.getenv('QA_SCREENSHOTS'):
        dest = Path(os.environ['QA_SCREENSHOTS'])
        dest.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest / name), full_page='desktop' not in name)


def test_move_shows_new_room_and_building(admin):
    page = admin
    def post(kind, payload):
        response = page.request.post('/api/admin/' + kind, data=payload)
        assert response.ok, response.text()
        return response.json()
    category = post('categories', {'name': 'Переезды QA', 'color': '#123456'})
    leader = post('leaders', {'name': 'Руководитель переезда', 'contact': '', 'position': ''})
    old = post('rooms', {'name': '901', 'building': 'Первый корпус', 'capacity': 10})
    new = post('rooms', {'name': '901', 'building': 'Второй корпус', 'capacity': 10})
    club = post('clubs', {'name': 'Кружок с длинным названием для проверки переноса и читаемости на телефоне', 'description': 'Описание', 'category_id': category['id'], 'leader_id': leader['id'], 'is_active': True})
    session = post('sessions', {'club_id': club['id'], 'room_id': old['id'], 'weekday': 2, 'start_time': '08:00', 'end_time': '09:00'})
    post('exceptions/moves', {'session_id': session['id'], 'original_date': '2027-01-05', 'new_date': '2027-01-06', 'new_start_time': '08:00', 'new_end_time': '09:00', 'new_room_id': new['id']})
    page.set_viewport_size({'width': 320, 'height': 740})
    page.goto(f"/club.html?id={club['id']}")
    expect(page.locator('.change-room')).to_have_text('Новая аудитория: 901 · Второй корпус')
    expect(page.locator('.slot-list')).to_contain_text('901 · Первый корпус')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not page.errors, page.errors
    shot(page, 'club-move-320.png')


def test_broadcast_retry_keeps_key_and_draft_and_sends_to_all(admin):
    page = admin
    requests = []
    def route_send(route):
        if route.request.method == 'POST':
            requests.append(route.request.post_data_json)
            if len(requests) == 1:
                route.fulfill(status=503, content_type='application/json', body='{"detail":"temporary failure"}')
            else:
                route.continue_()
        else:
            route.continue_()
    page.route('**/api/admin/broadcasts', route_send)
    page.goto('/admin/#/broadcasts')
    page.locator('#bc-title').fill('Объявление для всех QA')
    page.locator('#bc-body').fill('Проверяем повтор без второй рассылки')
    page.reload()
    expect(page.locator('#bc-title')).to_have_value('Объявление для всех QA')
    for attempt in range(2):
        page.get_by_role('button', name='Отправить…', exact=True).click()
        page.get_by_role('alertdialog').get_by_role('button', name='Отправить', exact=True).click()
        if attempt == 0:
            expect(page.locator('#bc-form .field-error')).to_be_visible()
            expect(page.locator('#bc-title')).to_have_value('Объявление для всех QA')
            page.reload()
            expect(page.locator('#bc-title')).to_have_value('Объявление для всех QA')
    expect(page.locator('#bc-title')).to_have_value('')
    assert len(requests) == 2
    assert requests[0]['idempotency_key'] == requests[1]['idempotency_key']
    assert all(r['audience'] == 'all' for r in requests)
    expect(page.locator('.bc-history')).to_contain_text('Объявление для всех QA')


def test_crud_draft_survives_reload_without_storing_passwords(admin):
    page = admin
    page.goto('/admin/#/clubs')
    page.get_by_role('button', name='Добавить кружок').click()
    page.locator('#f-name').fill('Несохранённый кружок QA')
    page.reload()
    page.get_by_role('button', name='Добавить кружок').click()
    expect(page.locator('#f-name')).to_have_value('Несохранённый кружок QA')
    page.get_by_role('button', name='Отмена', exact=True).click()
    page.evaluate('() => { window.ClubsAdmin.changePassword(); }')
    page.locator('#f-current_password').fill('SuperSecret-DoNotStore')
    assert 'SuperSecret-DoNotStore' not in page.evaluate('JSON.stringify(sessionStorage)')


def test_navigation_and_broadcast_at_320px(admin):
    page = admin
    page.set_viewport_size({'width': 320, 'height': 740})
    page.goto('/admin/#/broadcasts')
    expect(page.locator('#bc-title')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.bottom-nav a').evaluate_all('(links) => links.every(a => { const r = a.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.width >= 44; })')
    page.locator('#bc-title').fill('Короткое объявление')
    page.locator('#bc-body').fill('Проверка адаптивности')
    shot(page, 'admin-broadcast-320.png')
    assert not page.errors, page.errors


def test_dense_schedule_and_long_names_remain_readable(new_page):
    page = new_page()
    def dense(route):
        from urllib.parse import parse_qs, urlsplit
        week = parse_qs(urlsplit(route.request.url).query)['week'][0]
        events = [{'event_id': f'{i}:{week}', 'session_id': i, 'club_id': i,
                   'club_name': f'Параллельный кружок {i} с очень длинным названием для проверки читаемости',
                   'date': week, 'original_date': week, 'start_time': '10:00', 'end_time': '11:00',
                   'status': 'scheduled', 'category_color': '#123456', 'category_name': 'Направление',
                   'room_id': 1, 'room_name': '101', 'leader_name': f'Руководитель {i}'} for i in range(1, 41)]
        route.fulfill(json=events)
    page.route('**/api/schedule?*', dense)
    page.goto('/')
    expect(page.locator('.schedule-list .calendar-event')).to_have_count(40)
    assert page.locator('.week-grid').count() == 0
    assert page.locator('footer, .grid-crowded').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.calendar-event').first.click()
    expect(page.locator('#event-details')).to_contain_text('очень длинным названием')
    page.get_by_role('button', name='Закрыть', exact=True).click()
    shot(page, 'schedule-dense-desktop.png')
    assert not page.errors, page.errors


def test_legacy_state_redirects_without_losing_favorites(new_page):
    page = new_page(width=390, height=844)
    page.goto('/')
    page.evaluate("""() => {
      localStorage.setItem('itc.session', JSON.stringify({role:'teacher'}));
      localStorage.setItem('itc.role', 'teacher');
      localStorage.setItem('itc.follows', '[1,2]');
      localStorage.setItem('itc.pwa.announcements', '0');
    }""")
    page.goto('/teacher/index.html')
    page.wait_for_url('**/?from=legacy')
    assert page.evaluate("JSON.parse(localStorage.getItem('itc.session')).role") == 'guest'
    assert page.evaluate("localStorage.getItem('itc.follows')") == '[1,2]'
    assert page.evaluate("localStorage.getItem('itc.pwa.announcements')") == '0'
    assert page.locator('a[href*="attendance"], a[href*="qr.html"], a[href*="teacher/"]').count() == 0


def test_pwa_update_waits_for_draft_and_then_loads_fresh_assets(browser):
    from pwa.tests.pwa_env import Stand
    st = Stand()
    context = browser.new_context(base_url=st.base, viewport={'width': 390, 'height': 844}, bypass_csp=True)
    try:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        assert page.request.post('/api/admin/login', data={'login': 'admin', 'password': 'Demo-Pass-2026!'}).ok
        page.goto('/admin/#/broadcasts')
        page.wait_for_function('() => navigator.serviceWorker.controller && window.ClubsUpdates')
        page.locator('#bc-title').fill('Черновик во время обновления')
        page.locator('#bc-body').fill('Не потерять введённый текст')
        info = json.loads((st.www / 'build-info.json').read_text())
        old = info['build_id']
        new = old + '-qa-update'
        (st.www / 'build-info.json').write_text(json.dumps({'build_id': new}))
        worker = st.www / 'sw.js'
        worker.write_text(worker.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
        with (st.www / 'css/campus.css').open('a', encoding='utf-8') as f:
            f.write('\nhtml { --qa-build: updated; }\n')
        page.evaluate('window.ClubsUpdates.check({manual:true})')
        expect(page.locator('.app-update-notice')).to_contain_text('Сохраните')
        expect(page.locator('#bc-title')).to_have_value('Черновик во время обновления')
        page.wait_for_function('() => navigator.serviceWorker.getRegistration().then(r => !!r.waiting)')
        page.locator('#bc-title').fill('')
        page.locator('#bc-body').fill('')
        expect(page.locator('.app-update-notice button')).to_be_enabled()
        page.locator('.app-update-notice button').click()
        page.wait_for_function("() => getComputedStyle(document.documentElement).getPropertyValue('--qa-build').trim() === 'updated'")
        expect(page.locator('#bc-title')).to_have_value('')
        assert not errors, errors
        shot(page, 'pwa-updated-390.png')
    finally:
        context.close()
        st.stop()
