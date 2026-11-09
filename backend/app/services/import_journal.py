"""Atomic publication history and conflict-aware rollback for schedule imports."""
from __future__ import annotations

import json
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import DB_PATH, Base
from ..models.broadcast import AppDevice, Broadcast
from ..models.import_draft import ImportDraft
from ..models.import_publication import SCHEDULE_KEYS, ImportPublication, ScheduleRowRevision
from . import conflicts
from . import occurrence_source as occ_src
from .broadcast import ids

MAX_PUBLIC_ID = (1 << 53) - 1  # Lossless JSON integer on web clients.


class RollbackError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def legacy_history() -> list[dict]:
    backup_dir = Path(os.getenv("CLUBS_BACKUP_DIR") or (
        "/backups" if Path("/backups").is_dir() and os.access("/backups", os.W_OK)
        else DB_PATH.parent / "backups"
    ))
    try:
        items = json.loads((backup_dir / "import-publish.json").read_text("utf-8"))["items"]
        return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), int)]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _metadata(row: ImportPublication) -> dict:
    return {
        **json.loads(row.metadata_json),
        "id": row.id,
        "created_at": row.created_at,
        "draft_id": row.draft_id,
        "rollback_available": not row.rolled_back,
    }


def history(db: Session) -> list[dict]:
    legacy = [{**item, "rollback_available": False} for item in legacy_history()]
    entries = db.scalars(select(ImportPublication).order_by(ImportPublication.created_at, ImportPublication.id))
    return legacy + [_metadata(row) for row in entries]


def find_draft(db: Session, draft_id: int) -> dict | None:
    row = db.scalar(select(ImportPublication).where(ImportPublication.draft_id == draft_id))
    if row is not None:
        return _metadata(row)
    return next((item for item in reversed(legacy_history()) if item.get("draft_id") == draft_id), None)


def begin(db: Session) -> None:
    # Reserve the SQLite write transaction before reading any schedule state.
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _key(row: dict, columns: tuple[str, ...]) -> str:
    return json.dumps([row[column] for column in columns], separators=(",", ":"))


def capture(db: Session) -> dict:
    db.flush()
    conn = db.connection()
    return {
        table: {_key(row, columns): dict(row) for row in conn.exec_driver_sql(f'SELECT * FROM "{table}"').mappings()}
        for table, columns in SCHEDULE_KEYS.items()
    }


def _revisions(db: Session) -> dict:
    return {(row.table_name, row.row_key): row.revision for row in db.scalars(select(ScheduleRowRevision))}


def _new_entry(db: Session, metadata: dict, changes: dict, draft_id: int | None = None) -> ImportPublication:
    legacy_ids = {item["id"] for item in legacy_history()}
    while True:
        # A restored database must not reassign a known publication ID to new work.
        publish_id = (1 << 52) + secrets.randbits(52)
        if publish_id not in legacy_ids and db.get(ImportPublication, publish_id) is None:
            break
    row = ImportPublication(
        id=publish_id, created_at=datetime.now(timezone.utc).isoformat(),
        draft_id=draft_id, metadata_json=json.dumps(metadata, ensure_ascii=False),
        changes_json=json.dumps(changes, ensure_ascii=False), rolled_back=False,
    )
    db.add(row)
    db.flush()
    return row


def record(db: Session, before: dict, *, author: str, stats: dict, draft_id: int | None = None) -> dict:
    after = capture(db)
    revisions = _revisions(db)
    changes = {}
    for table, previous in before.items():
        current = after[table]
        rows = {
            key: {"before": previous.get(key), "after": current.get(key), "revision": revisions[(table, key)]}
            for key in sorted(previous.keys() | current.keys())
            if previous.get(key) != current.get(key)
        }
        if rows:
            changes[table] = rows
    assigned_clubs = {
        item["after"]["id"] for item in changes.get("clubs", {}).values()
        if item["before"] and item["after"] and item["before"]["leader_id"] != item["after"]["leader_id"]
    }
    for item in changes.get("club_leaders", {}).values():
        link = item["after"] or item["before"]
        if _key({"id": link["club_id"]}, ("id",)) in before["clubs"]:
            assigned_clubs.add(link["club_id"])
    watched = _club_sessions(after, revisions, assigned_clubs)
    journal = {"rows": changes, "assigned_clubs": sorted(assigned_clubs), "watched_sessions": watched}
    return _metadata(_new_entry(db, {"author": author, "stats": stats}, journal, draft_id))


def _club_sessions(snapshot: dict, revisions: dict, clubs: set[int]) -> dict:
    return {
        key: revisions.get(("sessions", key))
        for key, row in snapshot["sessions"].items() if row["club_id"] in clubs
    }



def _check_logical_dependencies(db: Session, removed: dict[str, set[int]], created_at: str) -> None:
    clubs = removed["clubs"]
    sessions = removed["sessions"]
    if clubs:
        # Anonymous polling used to accept nonexistent club IDs. Only device
        # preferences recorded since the club existed are dependencies.
        published_at = datetime.fromisoformat(created_at).replace(tzinfo=None)
        devices = db.scalars(select(AppDevice.club_ids).where(AppDevice.last_seen >= published_at))
        if any(clubs.intersection(ids(raw)) for raw in devices):
            raise RollbackError(409, "На опубликованные кружки ссылаются подписки")
    if clubs or sessions:
        rows = db.execute(select(Broadcast.club_ids, Broadcast.session_ids))
        if any(clubs.intersection(ids(c)) or sessions.intersection(ids(s)) for c, s in rows):
            raise RollbackError(409, "На опубликованные записи ссылаются объявления")

    choices = db.scalars(select(ImportDraft.decisions_json).where(ImportDraft.status == "draft"))
    for raw in choices:
        for choice in json.loads(raw):
            if choice.get("action") != "create":
                continue
            references = {
                "clubs": [choice.get("club_id")],
                "categories": [choice.get("category_id")],
                "leaders": [choice.get("leader_id"), *choice.get("leader_ids", [])],
                "rooms": choice.get("room_ids", []),
            }
            if any(removed.get(table, set()).intersection(values) for table, values in references.items()):
                raise RollbackError(409, "На опубликованные записи ссылается черновик импорта")


def _conflict_windows(before: occ_src.Snapshot, after: occ_src.Snapshot):
    start, end = occ_src.default_window(before)
    windows = [(start, end)]
    periods = getattr(after.calendar, "periods", ())
    dates = {end, *(period.ends_on for period in periods)}
    windows.extend((max(start, p.starts_on), p.ends_on) for p in periods if p.ends_on > end)
    for snap in (before, after):
        dates.update(occ_src._d(item.one_off_date) for item in snap.sessions.values() if item.one_off_date)
        for item in snap.exceptions:
            dates.add(occ_src._d(item.original_date))
            if item.new_date:
                dates.add(occ_src._d(item.new_date))
    # Include a full parity cycle after exceptional dates and period boundaries.
    for day in dates:
        windows.append((day, day + timedelta(days=min(14, (date.max - day).days))))
    merged = []
    for low, high in sorted(windows):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    yield from merged


def _apply_undo(db: Session, changes: dict) -> None:
    conn = db.connection()
    for table, columns in SCHEDULE_KEYS.items():
        predicate = " AND ".join(f'"{column}" = ?' for column in columns)
        for key, change in changes.get(table, {}).items():
            before = change["before"]
            if before is None:
                continue
            if change["after"] is None:
                names = ", ".join(f'"{name}"' for name in before)
                values = ", ".join("?" for _ in before)
                conn.exec_driver_sql(f'INSERT INTO "{table}" ({names}) VALUES ({values})', tuple(before.values()))
            else:
                fields = {name: value for name, value in before.items() if name not in columns}
                assignments = ", ".join(f'"{name}" = ?' for name in fields)
                conn.exec_driver_sql(
                    f'UPDATE "{table}" SET {assignments} WHERE {predicate}',
                    (*fields.values(), *json.loads(key)),
                )
    for table, columns in reversed(SCHEDULE_KEYS.items()):
        for key, change in changes.get(table, {}).items():
            if change["before"] is not None:
                continue
            # Check remaining children before deleting so SQLite cannot cascade into later data.
            for child in Base.metadata.tables.values():
                for fk in child.foreign_key_constraints:
                    if fk.referred_table.name != table:
                        continue
                    predicate = " AND ".join(f'"{part.parent.name}" = ?' for part in fk.elements)
                    params = tuple(change["after"][part.column.name] for part in fk.elements)
                    if conn.exec_driver_sql(f'SELECT 1 FROM "{child.name}" WHERE {predicate} LIMIT 1', params).first():
                        raise RollbackError(409, "У опубликованной записи появились зависимости")
            predicate = " AND ".join(f'"{column}" = ?' for column in columns)
            conn.exec_driver_sql(f'DELETE FROM "{table}" WHERE {predicate}', tuple(json.loads(key)))


def rollback(db: Session, publish_id: int, *, author: str) -> dict:
    try:
        begin(db)
        row = db.get(ImportPublication, publish_id) if 0 < publish_id <= MAX_PUBLIC_ID else None
        if row is None:
            if any(item["id"] == publish_id for item in legacy_history()):
                raise RollbackError(410, "Откат старой публикации недоступен")
            raise RollbackError(404, "Публикация не найдена")
        if row.rolled_back:
            raise RollbackError(409, "Откат этой публикации уже выполнен или недоступен")
        journal = json.loads(row.changes_json)
        changes = journal["rows"]
        current = capture(db)
        revisions = _revisions(db)
        if _club_sessions(current, revisions, set(journal["assigned_clubs"])) != journal["watched_sessions"]:
            raise RollbackError(409, "После публикации изменились занятия кружка с обновлёнными руководителями")
        for table, rows in changes.items():
            for key, change in rows.items():
                if current[table].get(key) != change["after"] or revisions.get((table, key)) != change["revision"]:
                    raise RollbackError(409, "После публикации эти записи были изменены")
        store = conflicts.ConflictOverrides()
        allowed = store.load()
        removed = {
            table: {change["after"]["id"] for change in changes.get(table, {}).values() if change["before"] is None}
            for table in ("categories", "leaders", "rooms", "clubs", "sessions")
        }
        if any(removed["sessions"].intersection((item["session_a"], item["session_b"])) for item in allowed):
            raise RollbackError(409, "У опубликованного занятия появилось разрешение на пересечение")
        _check_logical_dependencies(db, removed, row.created_at)
        before = occ_src.load_snapshot(db)
        _apply_undo(db, changes)
        db.expire_all()
        after = occ_src.load_snapshot(db)
        for start, end in _conflict_windows(before, after):
            old_keys = {item.key for item in conflicts.detect(before, occ_src.snapshot_occurrences(before, start, end))}
            if any(item.key not in old_keys and not store.allows(item, allowed)
                   for item in conflicts.detect(after, occ_src.snapshot_occurrences(after, start, end))):
                raise RollbackError(409, "Откат создаёт пересечение в расписании")
        row.rolled_back = True
        entry = _new_entry(db, {"author": author, "rollback_of": publish_id, "stats": {}}, {})
        entry.rolled_back = True
        db.flush()
        result = _metadata(entry)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise RollbackError(409, "Откат конфликтует с текущими данными") from exc
    except Exception:
        db.rollback()
        raise
