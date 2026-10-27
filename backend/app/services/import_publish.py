"""Публикация нормализованного набора импорта (контракт: docs/schedule-v2-contract.md §5).

* идемпотентно: сопоставление по нормализованному названию кружка, ФИО ведущего,
  (корпус, номер) аудитории, названию категории; повторная публикация того же набора
  ничего не меняет и дублей не создаёт;
* одной транзакцией; перед записью — проверка движком конфликтов (новые пересечения → отказ);
* перед публикацией — автоматический бэкап (cli.backup, префикс pre-import), откат —
  восстановлением этого снимка (rollback()).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from ..models.category import Category
from ..models.club import Club
from ..models.leader import Leader
from ..models.room import Room
from ..models.session import ClubSession
from . import conflicts as engine
from . import occurrence_source as occ_src

TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_COLOR = "#64748b"


class ImportError_(ValueError):
    def __init__(self, message: str, *, errors: list[str] | None = None, conflicts: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []
        self.conflicts = conflicts or []


def norm(value: Any) -> str:
    """Нормализация ключа сопоставления: регистр, ё→е, пробелы, кавычки, точки инициалов."""
    s = str(value or "").replace("ё", "е").replace("Ё", "Е")
    s = re.sub(r"[«»\"'“”]", "", s)
    s = re.sub(r"\s*\.\s*", ". ", s)
    return re.sub(r"\s+", " ", s).strip().casefold().rstrip(".").strip()


def backup_dir() -> Path:
    env = os.getenv("CLUBS_BACKUP_DIR")
    if env:
        return Path(env)
    if Path("/backups").is_dir() and os.access("/backups", os.W_OK):
        return Path("/backups")
    from ..database import DB_PATH

    return Path(DB_PATH).parent / "backups"


def _journal() -> Path:
    return backup_dir() / "import-publish.json"


def history() -> list[dict]:
    try:
        return json.loads(_journal().read_text("utf-8")).get("items", [])
    except (OSError, ValueError):
        return []


def _record(item: dict) -> dict:
    items = history()
    item["id"] = max((i.get("id", 0) for i in items), default=0) + 1
    items.append(item)
    path = _journal()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items[-200:]}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path)
    return item


# --------------------------------------------------------------------------- валидация


def validate(dataset: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(dataset, dict) or dataset.get("version") != 1:
        return ["version: ожидается 1"]
    for i, room in enumerate(dataset.get("rooms", [])):
        if not str(room.get("number", "")).strip():
            errors.append(f"rooms[{i}].number: пусто")
    for i, leader in enumerate(dataset.get("leaders", [])):
        if not str(leader.get("full_name", "")).strip():
            errors.append(f"leaders[{i}].full_name: пусто")
    leader_keys = {norm(l.get("full_name")) for l in dataset.get("leaders", [])}
    room_keys = {(norm(r.get("building")), norm(r.get("number"))) for r in dataset.get("rooms", [])}
    seen_clubs: set[str] = set()
    clubs = dataset.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        errors.append("clubs: ожидается непустой массив")
        return errors
    for i, club in enumerate(clubs):
        p = f"clubs[{i}]"
        key = norm(club.get("name"))
        if not key:
            errors.append(f"{p}.name: пусто")
        elif key in seen_clubs:
            errors.append(f"{p}.name: кружок «{club.get('name')}» встречается дважды")
        seen_clubs.add(key)
        if not str(club.get("category", "")).strip():
            errors.append(f"{p}.category: пусто")
        leaders = club.get("leaders") or []
        if not leaders:
            errors.append(f"{p}.leaders: нужен хотя бы один ведущий")
        for name in leaders:
            if norm(name) not in leader_keys:
                errors.append(f"{p}.leaders: «{name}» нет в leaders[]")
        for j, s in enumerate(club.get("sessions") or []):
            q = f"{p}.sessions[{j}]"
            repeat = s.get("repeat", "weekly")
            if repeat not in occ_src.REPEAT_VALUES:
                errors.append(f"{q}.repeat: weekly|even|odd|once")
            pid = s.get("period_id")
            if pid is not None and (not isinstance(pid, int) or pid <= 0):
                errors.append(f"{q}.period_id: id учебного периода")
            if repeat in ("even", "odd") and pid is None:
                errors.append(f"{q}.period_id: чётные/нечётные занятия относятся к учебному периоду")
            if repeat == "once":
                if not DATE_RE.match(str(s.get("date") or "")):
                    errors.append(f"{q}.date: для once нужна дата YYYY-MM-DD")
            elif not isinstance(s.get("weekday"), int) or not 1 <= s["weekday"] <= 6:
                errors.append(f"{q}.weekday: 1..6")
            start, end = str(s.get("start", "")), str(s.get("end", ""))
            if not TIME_RE.match(start) or not TIME_RE.match(end) or start >= end:
                errors.append(f"{q}: время HH:MM, начало раньше конца")
            rooms = s.get("rooms") or []
            if not rooms:
                errors.append(f"{q}.rooms: нужна аудитория")
            for r in rooms:
                if (norm(r.get("building")), norm(r.get("number"))) not in room_keys:
                    errors.append(f"{q}.rooms: ({r.get('building')}, {r.get('number')}) нет в rooms[]")
            for name in s.get("leaders") or []:
                if norm(name) not in leader_keys:
                    errors.append(f"{q}.leaders: «{name}» нет в leaders[]")
    return errors


# --------------------------------------------------------------------------- применение


def _columns(db: Session, table: str) -> dict[str, dict]:
    insp = inspect(db.get_bind())
    if table not in insp.get_table_names():
        return {}
    return {c["name"]: c for c in insp.get_columns(table)}


def _apply(db: Session, dataset: dict, *, prune: bool) -> dict:
    stats = {k: 0 for k in ("categories_created", "leaders_created", "rooms_created", "clubs_created",
                            "clubs_updated", "sessions_created", "sessions_kept", "sessions_deleted")}
    room_cols = _columns(db, "rooms")
    session_cols = _columns(db, "sessions")
    has_repeat = "repeat" in session_cols

    categories = {norm(c.name): c for c in db.scalars(select(Category))}
    leaders = {norm(l.name): l for l in db.scalars(select(Leader))}
    rooms = {(norm(r.building), norm(r.name)): r for r in db.scalars(select(Room))}
    clubs = {norm(c.name): c for c in db.scalars(select(Club))}

    for item in dataset.get("leaders", []):
        key = norm(item["full_name"])
        leader = leaders.get(key)
        if leader is None:
            leader = Leader(name=" ".join(item["full_name"].split()), position=item.get("position") or "", contact=item.get("contact") or "")
            db.add(leader)
            leaders[key] = leader
            stats["leaders_created"] += 1
        else:
            for field in ("position", "contact"):
                if item.get(field):
                    setattr(leader, field, item[field])
    for item in dataset.get("rooms", []):
        key = (norm(item.get("building")), norm(item["number"]))
        room = rooms.get(key)
        if room is None:
            capacity = item.get("capacity")
            if capacity is None and not room_cols.get("capacity", {}).get("nullable", False):
                capacity = 0
            room = Room(name=str(item["number"]).strip(), building=str(item.get("building") or "").strip(), capacity=capacity)
            db.add(room)
            rooms[key] = room
            stats["rooms_created"] += 1
        elif item.get("capacity") is not None:
            room.capacity = item["capacity"]
        # T2: дистанционная аудитория; «link» набора — rooms.remote_url
        for key, column in (("is_remote", "is_remote"), ("link", "remote_url"), ("remote_url", "remote_url"), ("remote_instructions", "remote_instructions")):
            if column in room_cols and key in item and hasattr(room, column):
                setattr(room, column, item[key] if item[key] is not None else ("" if column != "is_remote" else False))
    db.flush()

    touched_sessions: set[int] = set()
    for item in dataset["clubs"]:
        cat_key = norm(item["category"])
        category = categories.get(cat_key)
        if category is None:
            category = Category(name=item["category"].strip(), color=item.get("category_color") or DEFAULT_COLOR)
            db.add(category)
            db.flush()
            categories[cat_key] = category
            stats["categories_created"] += 1
        club_leaders = [leaders[norm(n)] for n in item["leaders"]]
        key = norm(item["name"])
        club = clubs.get(key)
        if club is None:
            club = Club(name=" ".join(item["name"].split()), description=item.get("description") or "",
                        category_id=category.id, leader_id=club_leaders[0].id, is_active=item.get("is_active", True))
            db.add(club)
            db.flush()
            clubs[key] = club
            stats["clubs_created"] += 1
        else:
            changed = False
            for field, value in (("category_id", category.id), ("leader_id", club_leaders[0].id)):
                if getattr(club, field) != value:
                    setattr(club, field, value)
                    changed = True
            if item.get("description") is not None and club.description != item["description"]:
                club.description = item["description"]
                changed = True
            stats["clubs_updated"] += int(changed)
        _set_links(db, "club_leaders", "club_id", club.id, "leader_id", [l.id for l in club_leaders])

        existing = {(_session_sig(s, has_repeat)): s for s in db.scalars(select(ClubSession).where(ClubSession.club_id == club.id))}
        wanted: set[tuple] = set()
        for s in item.get("sessions") or []:
            repeat = s.get("repeat", "weekly")
            if repeat in ("even", "odd") and not has_repeat:
                raise ImportError_("Чётные/нечётные недели требуют миграции 0010 (sessions.repeat)")
            primary_room = rooms[(norm(s["rooms"][0].get("building")), norm(s["rooms"][0]["number"]))]
            one_off = s.get("date") if repeat == "once" else None
            weekday = datetime.fromisoformat(one_off).isoweekday() if one_off else s["weekday"]
            sig = (weekday, s["start"], s["end"], primary_room.id, one_off, repeat if has_repeat else None)
            wanted.add(sig)
            session = existing.get(sig)
            if session is None:
                fields = dict(club_id=club.id, room_id=primary_room.id, weekday=weekday, start_time=s["start"],
                              end_time=s["end"], one_off_date=one_off)
                if s.get("period_id") is not None and hasattr(ClubSession, "period_id"):
                    from ..models.period import AcademicPeriod

                    if db.get(AcademicPeriod, s["period_id"]) is None:
                        raise ImportError_(f"Учебный период {s['period_id']} не найден")
                    fields["period_id"] = s["period_id"]
                session = ClubSession(**fields)
                if has_repeat:
                    setattr(session, "repeat", repeat) if hasattr(ClubSession, "repeat") else None
                db.add(session)
                db.flush()
                if has_repeat and not hasattr(ClubSession, "repeat"):
                    db.execute(text("UPDATE sessions SET repeat = :r WHERE id = :i"), {"r": repeat, "i": session.id})
                existing[sig] = session
                stats["sessions_created"] += 1
            else:
                stats["sessions_kept"] += 1
            touched_sessions.add(session.id)
            room_ids = [rooms[(norm(r.get("building")), norm(r["number"]))].id for r in s["rooms"]]
            _set_links(db, "session_rooms", "session_id", session.id, "room_id", room_ids if len(room_ids) > 1 else [])
            names = s.get("leaders") or []
            _set_links(db, "session_leaders", "session_id", session.id, "leader_id", [leaders[norm(n)].id for n in names])
        if prune:
            for sig, session in list(existing.items()):
                if sig not in wanted:
                    db.delete(session)
                    stats["sessions_deleted"] += 1
    db.flush()
    stats["touched_session_ids"] = sorted(touched_sessions)
    return stats


def _session_sig(s: ClubSession, has_repeat: bool) -> tuple:
    repeat = getattr(s, "repeat", None) if has_repeat else None
    if has_repeat and repeat is None:
        repeat = "once" if s.one_off_date else "weekly"
    return (s.weekday, s.start_time, s.end_time, s.room_id, s.one_off_date, repeat)


def _set_links(db: Session, table: str, owner_col: str, owner_id: int, value_col: str, values: list[int]) -> None:
    cols = _columns(db, table)
    if not cols or owner_col not in cols or value_col not in cols:
        return
    db.execute(text(f"DELETE FROM {table} WHERE {owner_col} = :o"), {"o": owner_id})
    has_pos = "position" in cols
    for pos, value in enumerate(dict.fromkeys(values)):
        if has_pos:
            db.execute(text(f"INSERT INTO {table} ({owner_col}, {value_col}, position) VALUES (:o, :v, :p)"), {"o": owner_id, "v": value, "p": pos})
        else:
            db.execute(text(f"INSERT INTO {table} ({owner_col}, {value_col}) VALUES (:o, :v)"), {"o": owner_id, "v": value})


# --------------------------------------------------------------------------- публикация / откат


def publish(db: Session, dataset: dict, *, dry_run: bool = False, prune: bool = True, author: str = "", make_backup: bool = True) -> dict:
    errors = validate(dataset)
    if errors:
        raise ImportError_("Набор не прошёл проверку", errors=errors)
    before = occ_src.load_snapshot(db)
    start, end = occ_src.default_window(before)
    old_keys = {c.key for c in engine.detect(before, occ_src.snapshot_occurrences(before, start, end))}
    backup_path = None
    try:
        stats = _apply(db, dataset, prune=prune)
        after = occ_src.load_snapshot(db)
        touched = set(stats["touched_session_ids"])
        store = engine.ConflictOverrides()
        allowed = store.load()
        fresh = [
            c for c in engine.detect(after, occ_src.snapshot_occurrences(after, start, end))
            if c.key not in old_keys and (c.a.source_session_id in touched or c.b.source_session_id in touched)
            and not store.allows(c, allowed)
        ]
        if fresh:
            described = engine.merge_described([engine.describe(after, c, touched=touched) for c in fresh])
            raise ImportError_("Импорт создаёт пересечения в расписании", conflicts=described)
        if dry_run:
            db.rollback()
            return {"dry_run": True, "stats": stats}
    except Exception:
        db.rollback()
        raise
    db.rollback()  # снимок делаем с чистой БД, затем применяем заново в той же логике
    if make_backup:
        from .. import cli

        backup_path = cli.backup(backup_dir(), keep=30, prefix="pre-import")
    try:
        stats = _apply(db, dataset, prune=prune)
        db.commit()
    except Exception:
        db.rollback()
        raise
    entry = _record({
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "backup": backup_path.name if backup_path else None,
        "stats": {k: v for k, v in stats.items() if k != "touched_session_ids"},
    })
    return {"dry_run": False, "stats": stats, "publish": entry}


def backup_before_draft() -> Path:
    """Снимок БД перед публикацией черновика импорта T3 (/api/admin/imports/{id}/publish)."""
    from .. import cli

    return cli.backup(backup_dir(), keep=30, prefix="pre-import")


def record_draft_publish(draft_id: int, backup_path: Path | None, *, created: int, skipped: int, author: str = "") -> dict:
    """Запись в журнал публикаций: откат — POST /api/admin/import/publishes/{id}/rollback."""
    return _record({
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "draft_id": draft_id,
        "backup": backup_path.name if backup_path else None,
        "stats": {"sessions_created": created, "skipped": skipped},
    })


def rollback(publish_id: int) -> dict:
    item = next((i for i in history() if i.get("id") == publish_id), None)
    if item is None or not item.get("backup"):
        raise ImportError_("Публикация или её бэкап не найдены")
    path = backup_dir() / item["backup"]
    if not path.exists() or path.parent != backup_dir():
        raise ImportError_("Файл бэкапа отсутствует")
    from .. import cli

    result = cli.restore(path)
    _record({"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "rollback_of": publish_id, "backup": None, "stats": {}})
    return result
