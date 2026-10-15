"""Единое подключение к SQLite для страниц, API и служебных скриптов."""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
env_db_path = os.getenv("CLUBS_SCHEDULE_DB_PATH")
if env_db_path:
    candidate_path = Path(env_db_path)
    DB_PATH = (
        candidate_path.resolve()
        if candidate_path.is_absolute()
        else (ROOT / candidate_path).resolve()
    )
else:
    DB_PATH = ROOT / "development.sqlite3"
engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session

def init_db():
    from . import models  # noqa: F401

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
