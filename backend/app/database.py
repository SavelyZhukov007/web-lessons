"""Артём и Илья: единое подключение. Не создавайте свои engine в маршрутах."""
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path(__file__).resolve().parents[2] / "development.sqlite3"
engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as session:
        yield session

def init_db():
    # TODO: импортировать модели здесь перед create_all. Сейчас таблиц ещё нет.
    Base.metadata.create_all(engine)
