import base64
import io
import zipfile

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


def docx(rows):
    def cell(value):
        return f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>"
    body = "".join("<w:tr>" + "".join(cell(v) for v in row) + "</w:tr>" for row in rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>{body}</w:tbl></w:body></w:document>')
    return base64.b64encode(data.getvalue()).decode()


def test_import_preview_publish_and_repeat_protection(admin_client):
    world = make_world(admin_client)
    rows = [["День", "Кружок", "Руководитель", "Время", "Аудитория"], ["Вторник", "Новый кружок", "Кто-то", "13:00 – 14:00", "101"]]
    draft = _post(admin_client, "/api/admin/imports", {"filename": "schedule.docx", "content_base64": docx(rows)})
    assert draft["rows"][0]["weekday"] == 2
    assert admin_client.post(f"/api/admin/imports/{draft['id']}/publish").status_code == 409
    choice = {"row": 2, "action": "create", "category_id": world["category"]["id"], "leader_id": world["leader"]["id"], "room_ids": [world["room"]["id"]]}
    assert admin_client.put(f"/api/admin/imports/{draft['id']}/decisions", json={"decisions": [choice]}).status_code == 200
    published = admin_client.post(f"/api/admin/imports/{draft['id']}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["created"] == 1
    assert admin_client.post(f"/api/admin/imports/{draft['id']}/publish").status_code == 409


def test_import_conflict_rolls_back_earlier_rows(admin_client):
    world = make_world(admin_client)
    rows = [["День", "Кружок", "Руководитель", "Время", "Аудитория"], ["Вторник", "Создать", "Кто-то", "13:00–14:00", "101"], ["Понедельник", "Конфликт", "Кто-то", "10:00–11:00", "101"]]
    draft = _post(admin_client, "/api/admin/imports", {"filename": "schedule.docx", "content_base64": docx(rows)})
    choices = [{"row": i, "action": "create", "category_id": world["category"]["id"], "leader_id": world["leader"]["id"], "room_ids": [world["room"]["id"]]} for i in (2, 3)]
    admin_client.put(f"/api/admin/imports/{draft['id']}/decisions", json={"decisions": choices})
    response = admin_client.post(f"/api/admin/imports/{draft['id']}/publish")
    assert response.status_code == 409
    assert all(x["name"] != "Создать" for x in admin_client.get("/api/admin/clubs").json())


def test_xlsx_preview_reads_shared_and_inline_strings(admin_client):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Вторник</t></si><si><t>Кружок</t></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Заголовок</t></is></c></row><row r="2"><c r="A2" t="s"><v>0</v></c><c r="B2" t="s"><v>1</v></c><c r="C2" t="inlineStr"><is><t>Преподаватель</t></is></c><c r="D2" t="inlineStr"><is><t>10:00-11:00</t></is></c><c r="E2" t="inlineStr"><is><t>101</t></is></c></row></sheetData></worksheet>')
    result = _post(admin_client, "/api/admin/imports", {"filename": "schedule.xlsx", "content_base64": base64.b64encode(data.getvalue()).decode()})
    assert result["rows"][0]["club_name"] == "Кружок"
    assert result["rows"][0]["weekday"] == 2
