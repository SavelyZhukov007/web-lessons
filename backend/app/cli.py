"""Служебные команды (OPS-07, DB-04, DB-05): создание/сброс пароля админа, seed, бэкап, проверка конфигурации.
Запуск: `python server.py admin|seed|backup|check-config ...` (см. server.py). Все команды неинтерактивны, если пароль передан через
--password-stdin / переменную ADMIN_PASSWORD (иначе спрашиваем getpass)."""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

from sqlalchemy import delete, select

from . import settings
from .auth import hash_password, normalize_login, validate_password
from .database import DB_PATH, SessionLocal
from .migrations import prepare_database
from .models import Admin, AdminSession, Category, Club, ClubSession, Leader, Room, SessionException
from .services import audit
from .services.conflicts import intervals_overlap

ROOT = Path(__file__).resolve().parents[2]


class CliError(Exception):
    """Ожидаемая ошибка команды (печатается без трейсбека, код возврата 1)."""


# ---------------------------------------------------------------- администраторы
def _read_password(from_stdin: bool, login: str) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif os.getenv("ADMIN_PASSWORD"):
        password = os.environ["ADMIN_PASSWORD"]
    else:
        password = getpass("Пароль: ")
        if password != getpass("Повтори пароль: "):
            raise CliError("Пароли не совпадают")
    try:
        validate_password(password, login)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    return password


def create_admin(login: str, *, password_stdin: bool = False) -> str:
    try:
        login = normalize_login(login)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    password = _read_password(password_stdin, login)
    prepare_database()
    with SessionLocal() as db:
        if db.scalar(select(Admin).where(Admin.login == login)) is not None:
            raise CliError(f"Администратор «{login}» уже существует (сменить пароль: admin reset-password)")
        db.add(Admin(login=login, password_hash=hash_password(password)))
        db.commit()
    audit.log("admin_created_cli", login=login)
    return f"Администратор «{login}» создан."


def reset_password(login: str, *, password_stdin: bool = False) -> str:
    try:
        login = normalize_login(login)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    password = _read_password(password_stdin, login)
    prepare_database()
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.login == login))
        if admin is None:
            raise CliError(f"Администратор «{login}» не найден")
        admin.password_hash = hash_password(password)
        revoked = db.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id)).rowcount
        db.commit()
    audit.log("admin_password_reset_cli", login=login, revoked_sessions=revoked)
    return f"Пароль «{login}» изменён; завершено сессий: {revoked}."


def list_admins() -> str:
    prepare_database()
    with SessionLocal() as db:
        rows = db.scalars(select(Admin).order_by(Admin.login)).all()
    return "\n".join(f"{a.id}\t{a.login}\tсоздан {a.created_at:%Y-%m-%d}" for a in rows) or "Администраторов нет."


# ---------------------------------------------------------------- seed (DB-04)
def _need(item: dict, key: str, kind: str):
    if key not in item or item[key] in (None, ""):
        raise CliError(f"{kind}: нет обязательного поля «{key}» в {item!r}")
    return item[key]


def seed(path: Path | None = None, *, dry_run: bool = False) -> dict:
    """Идемпотентная загрузка data/sample-data.json. Ключи сопоставления — естественные (name, комбинация полей), id из файла
    используются только для связей внутри файла. Чужие записи не удаляются и не меняются; всё в одной транзакции."""
    path = path or (ROOT / "data" / "sample-data.json")
    if not path.exists():
        raise CliError(f"Файл не найден: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"{path}: некорректный JSON ({exc})") from exc
    prepare_database()
    stats = {k: {"created": 0, "existing": 0} for k in ("categories", "leaders", "rooms", "clubs", "sessions", "session_exceptions")}
    with SessionLocal() as db:
        try:
            cats, leaders, rooms, clubs, sessions = {}, {}, {}, {}, {}
            for item in data.get("categories", []):
                name = _need(item, "name", "category")
                obj = db.scalar(select(Category).where(Category.name == name))
                bucket = "existing" if obj else "created"
                obj = obj or Category(name=name, color=item.get("color") or "#606963")
                if bucket == "created":
                    db.add(obj)
                stats["categories"][bucket] += 1
                cats[item["id"]] = obj
            for item in data.get("leaders", []):
                name = _need(item, "name", "leader")
                obj = db.scalar(select(Leader).where(Leader.name == name, Leader.position == item.get("position", "")))
                bucket = "existing" if obj else "created"
                obj = obj or Leader(name=name, position=item.get("position", ""), contact=item.get("contact", ""))
                if bucket == "created":
                    db.add(obj)
                stats["leaders"][bucket] += 1
                leaders[item["id"]] = obj
            for item in data.get("rooms", []):
                name = _need(item, "name", "room")
                building = item.get("building", "")
                obj = db.scalar(select(Room).where(Room.name == name, Room.building == building))
                bucket = "existing" if obj else "created"
                obj = obj or Room(name=name, building=building, capacity=int(item.get("capacity", 1)))
                if bucket == "created":
                    db.add(obj)
                stats["rooms"][bucket] += 1
                rooms[item["id"]] = obj
            db.flush()
            for item in data.get("clubs", []):
                name = _need(item, "name", "club")
                try:
                    category, leader = cats[item["category_id"]], leaders[item["leader_id"]]
                except KeyError as exc:
                    raise CliError(f"Кружок «{name}»: нет {exc.args[0]!r} среди категорий/руководителей файла") from exc
                obj = db.scalar(select(Club).where(Club.name == name, Club.category_id == category.id))
                bucket = "existing" if obj else "created"
                obj = obj or Club(name=name, description=item.get("description", ""), category_id=category.id,
                                  leader_id=leader.id, is_active=bool(item.get("is_active", True)))
                if bucket == "created":
                    db.add(obj)
                stats["clubs"][bucket] += 1
                clubs[item["id"]] = obj
            db.flush()
            for item in data.get("sessions", []):
                try:
                    club, room = clubs[item["club_id"]], rooms[item["room_id"]]
                except KeyError as exc:
                    raise CliError(f"Занятие {item!r}: неизвестная ссылка {exc.args[0]!r}") from exc
                weekday, start, end = int(item["weekday"]), item["start_time"], item["end_time"]
                if not 1 <= weekday <= 7 or not start < end:
                    raise CliError(f"Занятие {item!r}: неверный день недели или время")
                obj = db.scalar(select(ClubSession).where(ClubSession.club_id == club.id, ClubSession.room_id == room.id,
                                                          ClubSession.weekday == weekday, ClubSession.start_time == start,
                                                          ClubSession.end_time == end))
                if obj is None:
                    for other in db.scalars(select(ClubSession).where(ClubSession.weekday == weekday)):
                        if intervals_overlap(start, end, other.start_time, other.end_time) and (
                                other.room_id == room.id or other.club.leader_id == club.leader_id):
                            raise CliError(f"Занятие {item!r} пересекается с уже существующим (id={other.id}) по аудитории или руководителю")
                    obj = ClubSession(club_id=club.id, room_id=room.id, weekday=weekday, start_time=start, end_time=end)
                    db.add(obj)
                    db.flush()
                    stats["sessions"]["created"] += 1
                else:
                    stats["sessions"]["existing"] += 1
                sessions[item["id"]] = obj
            for item in data.get("session_exceptions", []):
                try:
                    session, kind = sessions[item["session_id"]], item["type"]
                except KeyError as exc:
                    raise CliError(f"Исключение {item!r}: неизвестная ссылка {exc.args[0]!r}") from exc
                exists = db.scalar(select(SessionException).where(SessionException.session_id == session.id,
                                                                  SessionException.original_date == item["original_date"]))
                if exists:
                    stats["session_exceptions"]["existing"] += 1
                    continue
                new_room = rooms.get(item.get("new_room_id")) if kind == "moved" else None
                db.add(SessionException(session_id=session.id, original_date=item["original_date"], type=kind,
                                        new_date=item.get("new_date"), new_start_time=item.get("new_start_time"),
                                        new_end_time=item.get("new_end_time"), new_room_id=new_room.id if new_room else None,
                                        comment=item.get("comment", "")))
                stats["session_exceptions"]["created"] += 1
            if dry_run:
                db.rollback()
            else:
                db.commit()
        except CliError:
            db.rollback()
            raise
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise CliError(f"Загрузка отменена, БД не изменена: {exc}") from exc
    return stats


# ---------------------------------------------------------------- бэкап (DB-05)
def backup(dest: Path, *, keep: int = 14, compress: bool = True, prefix: str = "clubs") -> Path:
    """Консистентная копия SQLite через Online Backup API (безопасно при работающем сервере и WAL), проверка integrity_check, ротация."""
    prepare_database()
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    raw = dest / f"{prefix}-{stamp}.sqlite3"
    counter = 1
    while raw.exists() or raw.with_suffix(".sqlite3.gz").exists():  # две копии в одну секунду не затирают друг друга
        raw = dest / f"{prefix}-{stamp}-{counter}.sqlite3"
        counter += 1
    src = sqlite3.connect(str(DB_PATH))
    try:
        out = sqlite3.connect(str(raw))
        try:
            src.backup(out)
            result = out.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            out.close()
    finally:
        src.close()
    if result != "ok":
        raw.unlink(missing_ok=True)
        raise CliError(f"Бэкап не создан: integrity_check = {result}")
    final = raw
    if compress:
        final = raw.with_suffix(".sqlite3.gz")
        with raw.open("rb") as f_in, gzip.open(final, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        raw.unlink()
    # ротация только своего префикса: ночные clubs-*, pre-migrate-*, pre-import-* живут отдельно
    for old in sorted(dest.glob(f"{prefix}-[0-9]*.sqlite3*"), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)[keep:]:
        old.unlink()
    audit.log("backup_created", file=str(final))
    return final


def restore(path: Path, *, target: Path | None = None) -> dict:
    """Вернуть БД из бэкапа (.sqlite3 или .gz) через Online Backup API, проверив его до и после.

    Пишет в живую БД поверх (WAL-безопасно); перед этим проверяет integrity_check копии.
    Вызывать при остановленной записи (сервер остановлен или под schedule_write_lock).
    """
    if not path.exists():
        raise CliError(f"Файл не найден: {path}")
    import tempfile

    target = Path(target or DB_PATH)
    tmpdir = Path(tempfile.mkdtemp(prefix="clubs-restore-"))
    try:
        plain = tmpdir / "restore.sqlite3"
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as f_in, plain.open("wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(path, plain)
        src = sqlite3.connect(str(plain))
        try:
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CliError("Бэкап повреждён: integrity_check не ok")
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
                result = dst.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                dst.close()
        finally:
            src.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if result != "ok":
        raise CliError(f"После восстановления integrity_check = {result}")
    try:
        from .database import engine

        engine.dispose()  # соединения пула видели старую БД
    except Exception:  # noqa: BLE001
        pass
    audit.log("backup_restored", file=str(path))
    return {"restored_from": str(path), "integrity": result}


def verify_backup(path: Path) -> dict:
    """Проверка: файл открывается, integrity_check ok, схема на ревизии head, считаем строки (для «проверка восстановления»)."""
    if not path.exists():
        raise CliError(f"Файл не найден: {path}")
    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix="clubs-restore-"))
    try:
        target = tmpdir / "restore.sqlite3"
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as f_in, target.open("wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(path, target)
        conn = sqlite3.connect(str(target))
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            has_version = conn.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone()
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone() if has_version else None
            counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("categories", "leaders", "rooms", "clubs", "sessions", "session_exceptions", "admins")}
        finally:
            conn.close()
        from .migrations import head_revision
        return {"integrity": integrity, "revision": version[0] if version else None, "head": head_revision(), "rows": counts}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def check_config() -> list[str]:
    return settings.validate_for_startup(DB_PATH)
