"""Browser regressions for URL filters, calendar export and actual occurrences."""
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect


def test_catalog_filters_survive_reload_and_reset_preserves_other_params(new_page):
    page = new_page(width=390, height=844)
    club = page.request.get('/api/clubs').json()[0]
    page.goto('/clubs.html?source=lesson#public-main')
    search = page.locator('#club-search')
    search.fill(club['name'])
    page.locator('#club-category').select_option(str(club['category_id']))
    expect(page.locator('#content .club-card').first).to_be_visible()
    page.reload()
    expect(search).to_have_value(club['name'])
    expect(page.locator('#club-category')).to_have_value(str(club['category_id']))
    expect(page.locator('#content .club-card').first).to_be_visible()
    page.locator('#club-reset').click()
    expect(search).to_have_value('')
    assert parse_qs(urlparse(page.url).query) == {'source': ['lesson']}
    assert urlparse(page.url).fragment == 'public-main'
    assert not page.errors


def test_club_calendar_link_downloads_the_current_week(new_page):
    page = new_page()
    club = page.request.get('/api/clubs').json()[0]
    page.goto(f"/club.html?id={club['id']}")
    link = page.locator('a[href*="calendar.ics"]')
    expect(link).to_be_visible()
    assert 'week=' in link.get_attribute('href')
    with page.expect_download() as download:
        link.click()
    text = download.value.path().read_text(encoding='utf-8')
    assert 'BEGIN:VCALENDAR' in text and 'END:VCALENDAR' in text
    assert not page.errors


def test_attendance_choices_use_moved_occurrence_identity(admin):
    page = admin

    def post(path, body):
        response = page.request.post('/api/admin/' + path, data=body)
        assert response.status == 201, response.text()
        return response.json()

    category = post('categories', {'name': 'QR regression', 'color': '#123456'})
    leader = post('leaders', {'name': 'QR regression teacher', 'contact': '', 'position': ''})
    room = post('rooms', {'name': 'QR regression room', 'building': 'Test', 'capacity': 30})
    club = post('clubs', {'name': 'QR regression club', 'description': '', 'category_id': category['id'], 'leader_id': leader['id'], 'is_active': True})
    session = post('sessions', {'club_id': club['id'], 'room_id': room['id'], 'weekday': 1, 'start_time': '10:00', 'end_time': '11:00'})
    post('exceptions/moves', {'session_id': session['id'], 'original_date': '2027-11-01', 'new_date': '2027-11-02',
                            'new_start_time': '12:00', 'new_end_time': '13:00', 'new_room_id': room['id']})
    page.goto('/admin/#/attendance')
    date_input = page.get_by_label('Дата занятия', exact=True)
    expect(date_input).to_be_visible()
    date_input.fill('2027-11-02')
    date_input.press('Tab')
    select = page.get_by_label('Занятие', exact=True)
    expect(select).to_contain_text('QR regression club · перенос')
    select.select_option(f"{session['id']}:2027-11-01")
    page.get_by_role('button', name='Показать QR-код', exact=True).click()
    expect(page.locator('.attendance-qr-title')).to_contain_text('QR regression club')
    assert not page.errors
