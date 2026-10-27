from datetime import time


def intervals_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    """Полуинтервалы [start, end): совпадающие и вложенные пересекаются, «встык» (конец == начало) — нет."""
    return start_a < end_b and start_b < end_a


def find_conflicts(candidate: dict, events: list[dict], exclude_event_id: str | None = None) -> list[dict]:
    """Вход: события из контракта. Выход: [{event_id, reasons: [room, leader]}].
    Отменённые пропустить; сравнивать дату, действующие время и room_id.
    При редактировании исключать конкретное событие, не всю серию session_id.
    """
    conflicts = []
    for event in events:
        reasons = []
        if event["event_id"] == exclude_event_id:
            continue

        if event["status"] == "cancelled":
            continue

        if candidate["date"] != event["date"]:
            continue

        time_check = intervals_overlap(
            candidate["start_time"],
            candidate["end_time"],
            event["start_time"],
            event["end_time"],
        )

        if not time_check:
            continue

        if set(candidate.get("occupied_room_ids", candidate.get("room_ids") or [candidate["room_id"]])) & set(event.get("occupied_room_ids", event.get("room_ids") or [event["room_id"]])):
            reasons.append("room")

        if set(candidate.get("leader_ids") or [candidate["leader_id"]]) & set(event.get("leader_ids") or [event["leader_id"]]):
            reasons.append("leader")

        if reasons:
            conflicts.append({
                "event_id": event["event_id"],
                "reasons" : reasons,
            })

    return conflicts


# =========================================================================== schedule v2
# Движок конфликтов по реальным датам occurrence (occurrence_source). Ресурсы: аудитория
# (кроме дистанционных), каждый ведущий, группа (если есть session_groups). Проверка
# предлагаемого изменения = разница «после − до» в окне, поэтому старые (или разрешённые)
# пересечения не блокируют несвязанные правки.

import json  # noqa: E402
import threading  # noqa: E402
from dataclasses import dataclass as _dataclass  # noqa: E402
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta, timezone as _tz  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from types import SimpleNamespace as _NS  # noqa: E402
from typing import Any as _Any  # noqa: E402

from . import occurrence_source as _occ  # noqa: E402

RESOURCE_LABELS = {"room": "аудитория", "leader": "ведущий", "group": "группа"}
NEW_SESSION_ID = -1


@_dataclass(frozen=True)
class ScheduleConflict:
    date: _date
    resource: str  # room | leader | group
    resource_id: _Any
    a: "_occ.Occurrence"
    b: "_occ.Occurrence"

    @property
    def key(self) -> tuple:
        ends = sorted(
            [(o.source_session_id, o.key, o.date, o.start, o.end) for o in (self.a, self.b)]
        )
        return (self.resource, self.resource_id, tuple(ends))

    @property
    def pair(self) -> tuple[int, int]:
        x, y = sorted((self.a.source_session_id, self.b.source_session_id))
        return x, y


def _resources(snap, occ) -> list[tuple[str, _Any]]:
    out: list[tuple[str, _Any]] = []
    for room_id in occ.room_ids:
        if room_id is not None and not _occ.room_is_remote(snap, room_id):
            out.append(("room", room_id))
    for leader_id in occ.leader_ids:
        if leader_id is not None:
            out.append(("leader", leader_id))
    for group in occ.group_ids:
        out.append(("group", group))
    return out


def detect(snap, occurrences) -> list[ScheduleConflict]:
    buckets: dict[tuple, list] = {}
    for occ in occurrences:
        if not occ.occupies:
            continue
        for resource in _resources(snap, occ):
            buckets.setdefault((occ.date, *resource), []).append(occ)
    found: list[ScheduleConflict] = []
    for (day, kind, rid), items in buckets.items():
        items.sort(key=lambda o: (o.start, o.end, o.source_session_id))
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if b.start >= a.end:
                    break
                if a.source_session_id == b.source_session_id and a.key == b.key:
                    continue
                if intervals_overlap(a.start, a.end, b.start, b.end):
                    found.append(ScheduleConflict(day, kind, rid, a, b))
    found.sort(key=lambda c: (c.date, c.a.start, c.resource))
    return found


# --------------------------------------------------------------------------- разрешения


class ConflictOverrides:
    """«Разрешить совместное занятие»: пары серий (опц. конкретная дата) в JSON рядом с БД.

    Отдельный файл, а не таблица — чтобы не трогать sessions и не вклиниваться в цепочку
    миграций 0010–0012 (T1–T3). Перенос в таблицу — миграция 0013+ при необходимости.
    """

    _lock = threading.Lock()

    def __init__(self, path: _Path | None = None) -> None:
        if path is None:
            from ..database import DB_PATH

            path = _Path(DB_PATH).with_name("conflict-overrides.json")
        self.path = path

    def load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [item for item in data.get("items", []) if isinstance(item, dict)]

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.path)

    def add(self, session_a: int, session_b: int, *, on_date: str | None = None, comment: str = "") -> dict:
        a, b = sorted((int(session_a), int(session_b)))
        with self._lock:
            items = self.load()
            for item in items:
                if (item["session_a"], item["session_b"], item.get("date")) == (a, b, on_date):
                    return item
            item = {
                "id": max((i.get("id", 0) for i in items), default=0) + 1,
                "session_a": a,
                "session_b": b,
                "date": on_date,
                "comment": comment,
                "created_at": _datetime.now(_tz.utc).isoformat(timespec="seconds"),
            }
            items.append(item)
            self._save(items)
            return item

    def remove(self, override_id: int) -> bool:
        with self._lock:
            items = self.load()
            kept = [i for i in items if i.get("id") != override_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
            return True

    def prune(self, existing_session_ids: set[int]) -> None:
        with self._lock:
            items = self.load()
            kept = [i for i in items if i["session_a"] in existing_session_ids and i["session_b"] in existing_session_ids]
            if len(kept) != len(items):
                self._save(kept)

    def allows(self, conflict: ScheduleConflict, items: list[dict] | None = None) -> bool:
        a, b = conflict.pair
        day = conflict.date.isoformat()
        for item in items if items is not None else self.load():
            if (item["session_a"], item["session_b"]) == (a, b) and item.get("date") in (None, day):
                return True
        return False


# --------------------------------------------------------------------------- предлагаемые изменения


def _as_text(value):
    if isinstance(value, _date):
        return value.isoformat()
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return value


def apply_change(snap, operation: str, entity_id: int | None, payload: dict):
    """Применить изменение к копии снимка (те же операции, что ProposedChange)."""
    snap = snap.copy()
    payload = {k: _as_text(v) for k, v in (payload or {}).items()}
    touched: set[int] = set()
    if operation == "create_session":
        sid = entity_id if entity_id is not None else NEW_SESSION_ID
        fields = {"id": sid, "one_off_date": None, "repeat": None}
        fields.update(payload)
        fields["id"] = sid
        snap.sessions[sid] = _NS(**fields)
        for key, target in (("leader_ids", snap.session_leaders), ("room_ids", snap.session_rooms)):
            if payload.get(key):
                target[sid] = tuple(payload[key])
        touched.add(sid)
    elif operation == "update_session":
        session = snap.sessions.get(entity_id)
        if session is not None:
            for key, value in payload.items():
                setattr(session, key, value)
            # T2: доп. ведущие/аудитории занятия живут в session_leaders/session_rooms
            if "leader_ids" in payload:
                snap.session_leaders[entity_id] = tuple(payload["leader_ids"] or ())
            if "room_ids" in payload:
                snap.session_rooms[entity_id] = tuple(payload["room_ids"] or ())
            touched.add(entity_id)
    elif operation in ("create_cancel", "create_move"):
        snap.exceptions.append(
            _NS(
                id=None,
                session_id=payload["session_id"],
                original_date=payload["original_date"],
                type="cancelled" if operation == "create_cancel" else "moved",
                comment=payload.get("comment") or "",
                new_date=payload.get("new_date"),
                new_room_id=payload.get("new_room_id"),
                new_start_time=payload.get("new_start_time"),
                new_end_time=payload.get("new_end_time"),
            )
        )
        touched.add(payload["session_id"])
    elif operation == "update_move":
        for exc in snap.exceptions:
            if exc.id == entity_id:
                for key, value in payload.items():
                    setattr(exc, key, value)
                touched.add(exc.session_id)
    elif operation == "delete_exception":
        for exc in snap.exceptions:
            if exc.id == entity_id:
                touched.add(exc.session_id)
        snap.exceptions = [e for e in snap.exceptions if e.id != entity_id]
    elif operation in ("change_leader", "activate_club", "update_club"):
        club = snap.clubs.get(entity_id)
        if club is not None:
            if operation == "activate_club":
                club.is_active = True
            for key in ("leader_id", "is_active"):
                if key in payload:
                    setattr(club, key, payload[key])
            if "leader_ids" in payload:
                snap.club_leaders[entity_id] = tuple(payload["leader_ids"])
            touched.update(s.id for s in snap.sessions.values() if s.club_id == entity_id)
    else:
        raise ValueError(f"unknown operation {operation}")
    return snap, touched


def _explicit_dates(payload: dict) -> list[_date]:
    out = []
    for key, value in (payload or {}).items():
        if value and (key in ("original_date", "new_date", "one_off_date") or key.startswith("_exc_")):
            out.append(_occ._d(value))
    return out


def change_window(snap, payload: dict | None = None, *, today: _date | None = None) -> tuple[_date, _date]:
    start, end = _occ.default_window(snap, today=today)
    for day in _explicit_dates(payload or {}):
        start, end = min(start, day), max(end, day)
    return start, end


def check_change(
    db,
    operation: str,
    entity_id: int | None,
    payload: dict,
    *,
    snapshot=None,
    overrides: ConflictOverrides | None = None,
    today: _date | None = None,
) -> list[ScheduleConflict]:
    """Новые конфликты, которые появятся после изменения (с учётом разрешений)."""
    before = snapshot if snapshot is not None else _occ.load_snapshot(db)
    after, touched = apply_change(before, operation, entity_id, payload)
    extra = dict(payload or {})
    if operation in ("update_move", "delete_exception"):
        for exc in before.exceptions:
            if exc.id == entity_id:
                extra.setdefault("original_date", exc.original_date)
                extra.setdefault("new_date", exc.new_date)
                for value in (exc.original_date, exc.new_date):
                    if value:
                        extra[f"_exc_{value}"] = value
    start, end = change_window(before, extra, today=today)
    if not touched:
        return []
    old = {c.key for c in detect(before, _occ.snapshot_occurrences(before, start, end))}
    new = [
        c
        for c in detect(after, _occ.snapshot_occurrences(after, start, end))
        if c.key not in old and (c.a.source_session_id in touched or c.b.source_session_id in touched)
    ]
    allowed = (overrides or ConflictOverrides()).load()
    store = overrides or ConflictOverrides()
    return [c for c in new if not store.allows(c, allowed)]


def describe(snap, conflict: ScheduleConflict, *, touched: set[int] | None = None) -> dict:
    """Плоское описание для 409/админки. Поля event_id…reasons — совместимость с v1."""
    a, b = conflict.a, conflict.b
    if touched and a.source_session_id in touched and b.source_session_id not in touched:
        mine, other = a, b
    elif touched and b.source_session_id in touched and a.source_session_id not in touched:
        mine, other = b, a
    else:
        mine, other = a, b
    other_event = _occ.occurrence_event(snap, other) or {}
    mine_event = _occ.occurrence_event(snap, mine) or {}
    label = ""
    if conflict.resource == "room" and conflict.resource_id in snap.rooms:
        label = snap.rooms[conflict.resource_id].name
    elif conflict.resource == "leader" and conflict.resource_id in snap.leaders:
        label = snap.leaders[conflict.resource_id].name
    else:
        label = str(conflict.resource_id)
    return {
        "event_id": other.key,
        "club_name": other_event.get("club_name", ""),
        "date": conflict.date.isoformat(),
        "start_time": other.start,
        "end_time": other.end,
        "room_name": other_event.get("room_name", ""),
        "leader_name": other_event.get("leader_name", ""),
        "reasons": [conflict.resource],
        "resource": conflict.resource,
        "resource_id": conflict.resource_id,
        "resource_label": label,
        "session_id": mine.source_session_id,
        "other_session_id": other.source_session_id,
        "session": {**_brief(mine, mine_event)},
        "other": {**_brief(other, other_event)},
    }


def _brief(occ, event: dict) -> dict:
    return {
        "session_id": occ.source_session_id,
        "club_id": occ.club_id,
        "club_name": event.get("club_name", ""),
        "date": occ.date.isoformat(),
        "start_time": occ.start,
        "end_time": occ.end,
        "status": occ.status,
        "occurrence": occ.key,
    }


MAX_DATES_PER_CONFLICT = 20


def merge_described(items: list[dict]) -> list[dict]:
    """Склеить: одна запись на пару серий (+время); все даты — в ``dates``, ресурсы — в reasons.

    Поля event_id/date/… берутся у первой (ближайшей) даты — совместимость с v1.
    """
    merged: dict[tuple, dict] = {}
    for item in sorted(items, key=lambda i: i["date"]):
        key = (item["session_id"], item["other_session_id"], item["start_time"], item["end_time"], item["session"]["start_time"])
        if key in merged:
            row = merged[key]
            for reason in item["reasons"]:
                if reason not in row["reasons"]:
                    row["reasons"].append(reason)
            if item["date"] not in row["dates"]:
                row["dates_total"] += 1
                if len(row["dates"]) < MAX_DATES_PER_CONFLICT:
                    row["dates"].append(item["date"])
        else:
            merged[key] = {**item, "reasons": list(item["reasons"]), "dates": [item["date"]], "dates_total": 1}
    return list(merged.values())


def report(db, date_from: _date | None = None, date_to: _date | None = None, *, overrides: ConflictOverrides | None = None) -> dict:
    """Все пересечения в окне (для GET /api/admin/conflicts), разрешённые помечены allowed."""
    snap = _occ.load_snapshot(db)
    start, end = _occ.default_window(snap)
    start = date_from or start
    end = date_to or end
    store = overrides or ConflictOverrides()
    allowed_items = store.load()
    rows = []
    for conflict in detect(snap, _occ.snapshot_occurrences(snap, start, end)):
        row = describe(snap, conflict)
        row["allowed"] = store.allows(conflict, allowed_items)
        rows.append(row)
    return {"from": start.isoformat(), "to": end.isoformat(), "items": rows, "overrides": allowed_items}


def window_end(days: int) -> _date:
    from .clock import today_msk

    return today_msk() + _timedelta(days=days)
