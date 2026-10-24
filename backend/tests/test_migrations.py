"""DB-01/DB-03: миграции == модели; пустая БД и БД «как сейчас» (create_all без alembic_version) обновляются до head."""
import sqlite3

import pytest
from alembic import command
from sqlalchemy import inspect, text

from backend.app import migrations
from backend.app.database import Base, engine


@pytest.fixture
def real_migrations(monkeypatch):
    monkeypatch.delenv("CLUBS_USE_CREATE_ALL", raising=False)
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    yield
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(bind=engine)


def test_empty_db_upgrades_to_head_and_matches_models(real_migrations):
    migrations.prepare_database()
    assert migrations.current_revision() == migrations.head_revision() == "0005"
    command.check(migrations.alembic_config())  # «No new upgrade operations detected»
    tables = set(inspect(engine).get_table_names())
    assert {"clubs", "sessions", "push_subscriptions", "login_attempts", "admin_sessions"} <= tables


def test_existing_db_without_alembic_version_is_stamped_and_keeps_data(real_migrations):
    cfg = migrations.alembic_config()
    command.upgrade(cfg, "0001")  # «исходная» схема
    with engine.begin() as c:
        c.execute(text("INSERT INTO categories (name, color) VALUES ('Спорт', '#112233')"))
        c.execute(text("DROP TABLE alembic_version"))
    migrations.prepare_database()
    assert migrations.current_revision() == "0005"
    with engine.connect() as c:
        assert c.execute(text("SELECT name FROM categories")).scalar() == "Спорт"


def test_prepare_database_is_idempotent(real_migrations):
    migrations.prepare_database()
    migrations.prepare_database()
    assert migrations.current_revision() == "0005"


def test_db_rejects_garbage_time_and_date_formats(real_migrations):
    migrations.prepare_database()
    raw = engine.raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys=OFF")  # проверяем именно CHECK, а не FK
        bad_rows = [
            "INSERT INTO sessions (club_id, room_id, weekday, start_time, end_time) VALUES (1, 1, 1, '9:00', '10:00')",
            "INSERT INTO sessions (club_id, room_id, weekday, start_time, end_time) VALUES (1, 1, 1, 'ab:cd', 'zz:zz')",
            "INSERT INTO session_exceptions (session_id, original_date, type, comment) VALUES (1, 'вчера', 'cancelled', '')",
            "INSERT INTO session_exceptions (session_id, original_date, type, comment) VALUES (1, '2026/11/02', 'cancelled', '')",
        ]
        for sql in bad_rows:
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                raw.execute(sql)
        raw.execute("INSERT INTO sessions (club_id, room_id, weekday, start_time, end_time) VALUES (1, 1, 1, '09:00', '10:00')")
    finally:
        raw.rollback()
        raw.execute("PRAGMA foreign_keys=ON")  # соединение возвращается в общий пул — не оставляем FK выключенными
        raw.close()


def test_downgrade_and_upgrade_roundtrip(real_migrations):
    migrations.prepare_database()
    cfg = migrations.alembic_config()
    command.downgrade(cfg, "0001")
    assert "push_subscriptions" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert migrations.current_revision() == "0005"
