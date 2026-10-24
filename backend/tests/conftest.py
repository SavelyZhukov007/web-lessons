import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parents[2] / "test.sqlite3"
os.environ["CLUBS_SCHEDULE_DB_PATH"] = str(TEST_DB)
os.environ["ENV"] = "test"
os.environ["CLUBS_USE_CREATE_ALL"] = "1"  # быстрые тесты; миграции проверяет test_migrations.py
os.environ.setdefault("SCRYPT_LOG_N", "12")  # быстрые хэши в тестах; прод-параметры проверяются отдельно
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("VAPID_KEYS_FILE", str(TEST_DB.with_name("test_vapid_keys.json")))

from backend.app import models  # noqa: F401
from backend.app.database import Base, engine
from backend.app.main import app


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
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(TEST_DB) + suffix)
        if path.exists():
            path.unlink()
    vapid = TEST_DB.with_name("test_vapid_keys.json")
    if vapid.exists():
        vapid.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
