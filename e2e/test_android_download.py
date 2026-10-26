"""Страница установки использует опубликованный сервером APK, включая prerelease."""
from playwright.sync_api import expect


def test_android_download_uses_manifest_url_and_not_github_latest(new_page):
    page = new_page(width=390, height=844)
    page.route('**/api/app/android', lambda route: route.fulfill(json={
        'available': True, 'download_url': '/download/kipclub.apk', 'version': 'v1.0.012',
        'size': 1024, 'updated': '2026-10-26T00:00:00Z', 'sha256': 'ab' * 32,
    }))
    page.route('**/download/kipclub.apk', lambda route: route.fulfill(
        body=b'APK-test-fixture', content_type='application/vnd.android.package-archive',
        headers={'Content-Disposition': 'attachment; filename="kipclub.apk"'}))
    page.goto('/android/')
    expect(page.locator('#apk-meta')).to_contain_text('v1.0.012')
    expect(page.locator('#apk-download')).to_have_attribute('href', '/download/kipclub.apk')
    expect(page.locator('#apk-fallback')).to_be_visible()
    assert page.locator('a[href*="github.com"]').count() == 0
    with page.expect_download() as download:
        page.locator('#apk-download').click()
    assert download.value.suggested_filename == 'kipclub.apk'
    assert not page.errors, page.errors


def test_android_download_remains_available_when_metadata_fails(new_page):
    page = new_page()
    page.route('**/api/app/android', lambda route: route.abort())
    page.goto('/android/')
    expect(page.locator('#apk-meta')).to_contain_text('Не удалось проверить версию')
    expect(page.locator('#apk-download')).to_have_attribute('href', '/android/download')
    expect(page.locator('#apk-fallback')).to_be_visible()
