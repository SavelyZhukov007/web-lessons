"""Bounded schedule exports: actual occurrences, Unicode PDF and literal XLSX cells."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.sax.saxutils import escape

from . import occurrence_source as source

HEADERS = ["Дата", "Время (МСК)", "Кружок", "Аудитории", "Корпус", "Руководители", "Состояние"]


def rows(db, start: date, end: date, *, building: str = "", room_id: int | None = None):
    snap = source.load_snapshot(db)
    result = []
    for item in source.snapshot_occurrences(snap, start, end):
        if item.status == "moved_out":
            continue
        rms = [snap.rooms[i] for i in item.room_ids if i in snap.rooms]
        if room_id and room_id not in item.room_ids:
            continue
        if building and not any(getattr(r, "building", "") == building for r in rms):
            continue
        club = snap.clubs.get(item.club_id)
        result.append(
            [
                item.date.isoformat(),
                item.start + "–" + item.end,
                getattr(club, "name", "Занятие"),
                ", ".join(r.name for r in rms),
                ", ".join(dict.fromkeys(getattr(r, "building", "") for r in rms)),
                ", ".join(snap.leaders[i].name for i in item.leader_ids if i in snap.leaders),
                {"scheduled": "По расписанию", "cancelled": "Отменено", "moved_in": "Перенесено"}[item.status],
            ]
        )
    return sorted(result, key=lambda r: (r[0], r[1], r[2]))


def xlsx(rows):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = Element("worksheet", xmlns=ns)
    SubElement(sheet, "sheetViews").append(Element("sheetView", workbookViewId="0"))
    cols = SubElement(sheet, "cols")
    for i, width in enumerate((13, 18, 36, 24, 24, 32, 20), 1):
        SubElement(cols, "col", min=str(i), max=str(i), width=str(width), customWidth="1")
    data = SubElement(sheet, "sheetData")
    for index, row in enumerate([HEADERS, *rows], 1):
        record = SubElement(data, "row", r=str(index))
        for column, value in enumerate(row):
            cell = SubElement(record, "c", r=chr(65 + column) + str(index), t="inlineStr")
            # inlineStr, never a formula; leading =,+,-,@ remain literal text.
            SubElement(SubElement(cell, "is"), "t").text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
    SubElement(sheet, "autoFilter", ref=f"A1:G{len(rows) + 1}")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        z.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Расписание" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr("xl/worksheets/sheet1.xml", tostring(sheet, encoding="utf-8", xml_declaration=True))
    return out.getvalue()


def pdf(rows, title):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    if "GolosText" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("GolosText", str(Path(__file__).parents[1] / "assets/GolosText-Regular.ttf")))
    style = ParagraphStyle("body", fontName="GolosText", fontSize=8, leading=11)
    out = io.BytesIO()
    table = LongTable(
        [[Paragraph(escape(str(cell)), style) for cell in row] for row in [HEADERS, *rows]],
        colWidths=[61, 75, 165, 93, 90, 152, 90],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7edff")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b9c0cc")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    def footer(canvas, doc):
        canvas.setFont("GolosText", 8)
        canvas.drawRightString(815, 15, "KipClub · " + str(doc.page))

    SimpleDocTemplate(
        out, pagesize=landscape(A4), leftMargin=12, rightMargin=12, topMargin=20, bottomMargin=28, title=title, author="KipClub"
    ).build([Paragraph(escape(title), style), Spacer(1, 12), table], onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
