"""Alembic при старте (DB-01). Логика:
 - пустая БД → upgrade head;
 - БД создана раньше через create_all (есть таблицы, нет alembic_version) → stamp 0001 (исходная схема) и upgrade head;
 - ENV=test и CLUBS_USE_CREATE_ALL=1 → create_all (быстрые тесты); отдельный тест проверяет, что миграции == модели."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from .database import Base, engine

log = logging.getLogger("clubs.migrations")
BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE = "0001"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision() -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def prepare_database() -> None:
    if os.getenv("CLUBS_USE_CREATE_ALL") == "1":
        Base.metadata.create_all(bind=engine)
        return
    cfg = alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and tables - {"sqlite_sequence"}:
        log.warning("Найдена БД без alembic_version — помечаю как ревизию %s и применяю миграции", BASELINE)
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")
