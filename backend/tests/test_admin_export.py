from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from backend.app.services import admin_export

from .test_exception_conflicts_api import admin_client, make_world  # noqa: F401


def test_export_auth_bounds_and_room_building(admin_client):
    world = make_world(admin_client)
    params = {"date_from": "2026-11-09", "date_to": "2026-11-16"}
    data = admin_client.get("/api/admin/export", params=params).json()
    assert len(data["rows"]) == 2 and data["rows"][0][2] == "Python"
    assert admin_client.get("/api/admin/export", params={**params, "building": "Не этот корпус"}).json()["rows"] == []
    assert len(admin_client.get("/api/admin/export", params={**params, "room_id": world["room"]["id"]}).json()["rows"]) == 2
    assert admin_client.get("/api/admin/export", params={**params, "date_to": "2027-11-16"}).status_code == 422
    assert admin_client.get("/api/admin/export", params={**params, "date_to": "2026-11-08"}).status_code == 422
    for format, mime, prefix in [
        ("pdf", "application/pdf", b"%PDF-"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
    ]:
        response = admin_client.get("/api/admin/export", params={**params, "format": format})
        assert response.status_code == 200, response.text[:500]
        assert response.headers["content-type"].startswith(mime) and response.content.startswith(prefix)
        assert response.headers["cache-control"] == "no-store"


def test_xlsx_literal_strings_not_formulas_and_valid_xml():
    raw = admin_export.xlsx([["2026-11-09", "10:00–11:00", '=HYPERLINK("bad")', "101 & <", "Главный", "Иван\x00", "@literal"]])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            ET.fromstring(z.read(name))
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        assert root.findall(".//m:f", ns) == []
        values = [x.text for x in root.findall(".//m:t", ns)]
        assert '=HYPERLINK("bad")' in values and "101 & <" in values and "Иван" in values


def test_pdf_cyrillic_multi_page_and_empty():
    row = ["2026-11-09", "10:00–11:00", "Программирование на Python", "101", "Главный", "Иван Иванов", "Отменено"]
    for rows in [[], [row] * 180]:
        result = admin_export.pdf(rows, "Расписание КИПФИН")
        assert result.startswith(b"%PDF-") and b"GolosText" in result and b"/ToUnicode" in result
