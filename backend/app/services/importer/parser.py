import io
import re
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
WEEKDAYS = {name: i for i, name in enumerate(("понедельник", "вторник", "среда", "четверг", "пятница", "суббота"), 1)}


def xml(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD и сущности в документе запрещены")
    return ET.fromstring(data)


def word_cell(cell):
    paragraphs = []
    for paragraph in cell.findall(W + "p"):
        parts = []
        for item in paragraph.iter():
            if item.tag == W + "t":
                parts.append(item.text or "")
            elif item.tag in {W + "br", W + "cr"}:
                parts.append(" / ")
        value = "".join(parts).strip()
        if value:
            paragraphs.append(value)
    return " / ".join(paragraphs)


def read_rows(filename: str, content: bytes) -> list[dict]:
    if len(content) > 600_000 or len(content) < 4:
        raise ValueError("Размер файла должен быть не более 600 КБ")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(x.file_size for x in entries) > 10_000_000:
                raise ValueError("Документ слишком большой после распаковки")
            if filename.lower().endswith(".docx"):
                doc = xml(archive.read("word/document.xml"))
                table = doc.find(".//" + W + "tbl")
                if table is None:
                    raise ValueError("В документе нет таблицы")
                grid = [[word_cell(cell) for cell in row.findall(W + "tc")] for row in table.findall(W + "tr")]
            elif filename.lower().endswith(".xlsx"):
                shared = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    shared = ["".join(t.text or "" for t in item.iter(X + "t")) for item in xml(archive.read("xl/sharedStrings.xml")).findall(X + "si")]
                sheet = xml(archive.read("xl/worksheets/sheet1.xml"))
                grid = []
                for row in sheet.iter(X + "row"):
                    cells = [""] * 5
                    for cell in row.findall(X + "c"):
                        if cell.find(X + "f") is not None:
                            raise ValueError("Формулы в таблице не поддерживаются")
                        m = re.match(r"([A-Z]+)", cell.get("r", ""))
                        if not m:
                            continue
                        index = 0
                        for char in m.group(1):
                            index = index * 26 + ord(char) - 64
                        if not 1 <= index <= 5:
                            continue
                        text = cell.findtext(X + "v", default="")
                        if cell.get("t") == "s":
                            text = shared[int(text)]
                        elif cell.get("t") == "inlineStr":
                            text = "".join(t.text or "" for t in cell.iter(X + "t"))
                        cells[index - 1] = text
                    grid.append(cells)
            else:
                raise ValueError("Поддерживаются только DOCX и XLSX")
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError, ValueError) as exc:
        raise ValueError(f"Не удалось прочитать таблицу: {exc}") from exc
    result = []
    last_day = ""
    for index, cells in enumerate(grid[1:], 2):
        cells = [re.sub(r"\s+", " ", cell).strip() for cell in cells[:5]]
        if len(cells) != 5 or not any(cells):
            continue
        last_day = cells[0] or last_day
        times = re.search(r"(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})", cells[3])
        start = f"{int(times[1]):02}:{times[2]}" if times else None
        end = f"{int(times[3]):02}:{times[4]}" if times else None
        issues = []
        if last_day.lower() not in WEEKDAYS or not times or not cells[1]:
            issues.append("Не удалось распознать день, название или время")
        if re.search(r"неч[её]тн|ч[её]тн", cells[3], re.I):
            issues.append("Уточните учебный период и правило чередования")
        if '/' in cells[2] or '/' in cells[4]:
            issues.append("Проверьте нескольких руководителей или аудиторий")
        result.append({"row": index, "weekday": WEEKDAYS.get(last_day.lower()), "club_name": cells[1], "leaders": cells[2], "time_text": cells[3], "start_time": start, "end_time": end, "rooms": cells[4], "issues": issues})
    if not result or len(result) > 500:
        raise ValueError("Таблица должна содержать от 1 до 500 строк")
    for i, first in enumerate(result):
        for second in result[i + 1:]:
            if not first["start_time"] or not second["start_time"] or first["weekday"] != second["weekday"]:
                continue
            if first["start_time"] >= second["end_time"] or second["start_time"] >= first["end_time"]:
                continue
            same_room = first["rooms"] and first["rooms"].casefold() == second["rooms"].casefold()
            same_leader = first["leaders"] and first["leaders"].casefold() == second["leaders"].casefold()
            if same_room or same_leader:
                reason = "аудитория" if same_room else "руководитель"
                first["issues"].append(f"Возможное пересечение: строка {second['row']} ({reason})")
                second["issues"].append(f"Возможное пересечение: строка {first['row']} ({reason})")
    return result
