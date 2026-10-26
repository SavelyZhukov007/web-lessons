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


def test_broadcast_screen_sends_to_selected_club(admin):
    page = admin

    def post(path, body):
        response = page.request.post('/api/admin/' + path, data=body)
        assert response.status == 201, response.text()
        return response.json()

    category = post('categories', {'name': 'Рассылка e2e', 'color': '#123456'})
    leader = post('leaders', {'name': 'Рассылка e2e руководитель', 'contact': '', 'position': ''})
    club = post('clubs', {'name': 'Рассылка e2e кружок', 'description': '', 'category_id': category['id'], 'leader_id': leader['id'], 'is_active': True})
    page.goto('/admin/#/broadcasts')
    page.get_by_label('Заголовок', exact=False).first.fill('Проверка e2e')
    page.get_by_label('Текст', exact=False).first.fill('Занятие переносится на 15:00')
    page.get_by_role('radio', name='Кружкам').click()
    page.locator('#bc-search').fill(club['name'])
    page.get_by_role('checkbox', name=club['name'], exact=True).check()
    page.get_by_role('button', name='Отправить').first.click()
    page.get_by_role('alertdialog').get_by_role('button', name='Отправить').click()
    expect(page.locator('#admin-main')).to_contain_text('Проверка e2e')
    assert not page.errors
