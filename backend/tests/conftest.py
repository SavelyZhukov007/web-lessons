import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parents[2] / "test.sqlite3"
os.environ["CLUBS_SCHEDULE_DB_PATH"] = str(TEST_DB)

from backend.app import models  # noqa: F401
from backend.app.database import Base, engine
from backend.app.main import app
from backend.app.routers import admin as admin_router


@pytest.fixture(autouse=True)
def isolated_login_attempts(monkeypatch):
    # Каждый тест начинает с чистого счётчика, включая тесты блокировки входа.
    monkeypatch.setattr(admin_router, "login_attempts_by_ip", {})


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def cleanup_database_file():
    yield
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
