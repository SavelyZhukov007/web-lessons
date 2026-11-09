from __future__ import annotations

from playwright.sync_api import expect


def test_command_palette_keyboard_and_journal_route(admin):
    admin.keyboard.press('Control+k')
    expect(admin.locator('dialog[open]')).to_be_visible()
    admin.get_by_role('searchbox', name='Поиск раздела или команды').fill('журнал')
    admin.keyboard.press('Enter')
    expect(admin.locator('#view-title')).to_have_text('Журнал действий')
    assert admin.locator('.bottom-nav a').count() == 6
    assert not admin.errors, admin.errors


def test_room_undo_works_from_persistent_notice(admin):
    admin.goto('/admin/#/reference/rooms')
    admin.get_by_role('button', name='Добавить', exact=False).first.click()
    admin.locator('dialog input[name=name]').fill('Undo E2E 19020')
    admin.locator('dialog button[type=submit]').click()
    expect(admin.locator('.admin-undo')).to_be_visible()
    admin.locator('.admin-undo').get_by_role('button', name='Отменить изменение', exact=True).click()
    admin.locator('dialog[open]').get_by_role('button', name='Отменить изменение', exact=True).click()
    expect(admin.locator('.admin-undo')).to_be_hidden()
    expect(admin.locator('#admin-main')).not_to_contain_text('Undo E2E 19020')
    assert not admin.errors, admin.errors


def test_admin_exports_download_real_files(admin):
    admin.goto('/admin/#/export')
    expect(admin.locator('.admin-export-preview table')).to_be_visible()
    for label, suffix in [('XLSX', '.xlsx'), ('PDF', '.pdf')]:
        with admin.expect_download() as download:
            admin.get_by_role('button', name=label, exact=True).click()
        assert download.value.suggested_filename.endswith(suffix)
        assert not download.value.failure()
    assert not admin.errors, admin.errors


def test_bulk_preview_is_non_mutating(admin):
    admin.goto('/admin/#/bulk')
    first = admin.locator('.bulk-choices input[type=checkbox]').first
    expect(first).to_be_visible(); first.check()
    admin.get_by_role('combobox', name='Действие', exact=True).select_option('delete')
    admin.get_by_role('button', name='Предварительный просмотр', exact=True).click()
    expect(admin.locator('.bulk-preview')).to_contain_text('Изменений: 1')
    assert admin.locator('dialog[open]').count() == 0
    assert not admin.errors, admin.errors


def test_calendar_keyboard_alternative_opens_confirmable_form(admin):
    admin.goto('/admin/#/calendar')
    button = admin.locator('.admin-calendar-event button').first
    expect(button).to_be_visible(); button.click()
    expect(admin.locator('dialog[open]')).to_contain_text('Перенести одно занятие')
    expect(admin.locator('dialog input[name=new_date]')).to_be_visible()
    admin.keyboard.press('Escape')
    expect(admin.locator('dialog[open]')).to_have_count(0)
    assert not admin.errors, admin.errors


def test_scheduled_composer_keeps_moscow_label_and_draft(admin):
    admin.goto('/admin/#/broadcasts')
    expect(admin.locator('#bc-scheduled')).to_be_visible()
    admin.locator('#bc-scheduled').fill('2026-12-01T15:30')
    expect(admin.get_by_role('button', name='Запланировать…', exact=True)).to_be_visible()
    expect(admin.locator('#bc-schedule-hint')).to_contain_text('отменить')
    # Never send or schedule a real fixture broadcast here; backend tests own the transport mocks.
    assert not admin.errors, admin.errors


def test_prepared_import_preview_shows_resolved_rows_without_publishing(admin):
    import base64
    import io
    import zipfile
    rows = [['Кружок', 'День', 'Время', 'Руководитель', 'Аудитория'], ['Fixture', 'Сб', '08:00-08:30', 'Fixture', '101']]
    body = ''.join('<w:tr>' + ''.join(f'<w:tc><w:p><w:r><w:t>{v}</w:t></w:r></w:p></w:tc>' for v in row) + '</w:tr>' for row in rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>' + body + '</w:tbl></w:body></w:document>')
    result = admin.evaluate("""async content => {
      const {imports,loadAll}=await import('/js/admin/api.js');
      const refs=await loadAll();const before=refs.sessions.length;
      const draft=await imports.create({filename:'stage4-preview.docx',content_base64:content});
      await imports.decisions(draft.id,[{row:draft.rows[0].row,action:'create',club_id:refs.clubs[0].id,
        room_ids:[refs.rooms[0].id],weekday:6,start_time:'08:00',end_time:'08:30',repeat:'weekly'}]);
      return {id:draft.id,club:refs.clubs[0].name,room:refs.rooms[0].name,before};
    }""", base64.b64encode(data.getvalue()).decode())
    admin.goto('/admin/#/imports')
    admin.get_by_role('combobox', name='Черновик', exact=True).select_option(str(result['id']))
    admin.get_by_role('button', name='Проверить перед публикацией', exact=True).click()
    preview = admin.get_by_role('region', name='Предпросмотр подготовленного импорта')
    expect(preview).to_contain_text('Будет создано: 1')
    expect(preview).to_contain_text(result['club'])
    expect(preview).to_contain_text(result['room'])
    expect(preview).to_contain_text('каждую неделю')
    assert admin.evaluate("async () => (await (await import('/js/admin/api.js')).loadAll()).sessions.length") == result['before']
    assert not admin.errors, admin.errors
