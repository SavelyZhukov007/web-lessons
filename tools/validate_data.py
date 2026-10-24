"""Проверка файла демо-данных (data/demo-data.json): уникальность id, ссылочная целостность, форматы.

    python tools/validate_data.py data/demo-data.json      # код выхода 0 — всё хорошо, 1 — есть ошибки, 2 — файл не читается
"""
from __future__ import annotations

import argparse
import json
import re
import sys

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COLLECTIONS = ("categories", "leaders", "rooms", "clubs", "sessions")


def _ids(items: list, name: str, errors: list[str]) -> set:
    seen: set = set()
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            errors.append(f"{name}: запись без id: {item!r}")
            continue
        if item["id"] in seen:
            errors.append(f"{name}: повторяющийся id = {item['id']}")
        seen.add(item["id"])
    return seen


def validate(data: dict) -> list[str]:
    """Возвращает список ошибок (пустой — данные корректны)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["корень файла должен быть объектом"]
    ids = {}
    for name in COLLECTIONS:
        items = data.get(name)
        if not isinstance(items, list):
            errors.append(f"{name}: ожидается список")
            items = []
        ids[name] = _ids(items, name, errors)
    for club in data.get("clubs", []):
        for field, target in (("category_id", "categories"), ("leader_id", "leaders")):
            if club.get(field) is not None and club[field] not in ids[target]:
                errors.append(f"clubs[{club.get('id')}].{field} = {club[field]} не найден в {target}")
    for s in data.get("sessions", []):
        sid = s.get("id")
        if s.get("club_id") not in ids["clubs"]:
            errors.append(f"sessions[{sid}].club_id = {s.get('club_id')} не найден в clubs")
        if s.get("room_id") not in ids["rooms"]:
            errors.append(f"sessions[{sid}].room_id = {s.get('room_id')} не найден в rooms")
        if s.get("weekday") not in range(1, 7):
            errors.append(f"sessions[{sid}].weekday = {s.get('weekday')} (нужно 1..6)")
        start, end = s.get("start_time"), s.get("end_time")
        if not (isinstance(start, str) and TIME_RE.match(start) and isinstance(end, str) and TIME_RE.match(end)):
            errors.append(f"sessions[{sid}]: время должно быть HH:MM ({start!r}–{end!r})")
        elif start >= end:
            errors.append(f"sessions[{sid}]: начало {start} не раньше конца {end}")
    for e in data.get("session_exceptions", []):
        if not (isinstance(e.get("original_date"), str) and DATE_RE.match(e["original_date"])):
            errors.append(f"session_exceptions[{e.get('id')}].original_date должен быть YYYY-MM-DD")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка файла демо-данных")
    parser.add_argument("filename")
    args = parser.parse_args(argv)
    try:
        with open(args.filename, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"Не удалось прочитать {args.filename}: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    for line in errors:
        print(line)
    print("OK" if not errors else f"Найдено ошибок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
