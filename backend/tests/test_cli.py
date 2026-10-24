"""OPS-07 / DB-04 / DB-05: служебные команды и server.py CLI."""
import gzip
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app import cli
from backend.app.auth import verify_password
from backend.app.database import SessionLocal
from backend.app.models import Admin, AdminSession, Club, ClubSession

from .test_admin_functional_qa import admin_client  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Correct-horse-9"


def _write_password(monkeypatch, value=PASSWORD):
    monkeypatch.setenv("ADMIN_PASSWORD", value)


def test_create_admin_non_interactive_and_duplicate(monkeypatch):
    _write_password(monkeypatch)
    assert "создан" in cli.create_admin("Boss")
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.login == "boss"))  # логин нормализуется
        assert admin and verify_password(PASSWORD, admin.password_hash)
    with pytest.raises(cli.CliError, match="уже существует"):
        cli.create_admin("boss")


def test_create_admin_rejects_weak_password(monkeypatch):
    _write_password(monkeypatch, "short")
    with pytest.raises(cli.CliError):
        cli.create_admin("boss")


def test_reset_password_revokes_sessions(admin_client, monkeypatch):
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AdminSession.id))) >= 1
        login = db.scalar(select(Admin.login))
    _write_password(monkeypatch, "Brand-new-pass-77")
    assert "изменён" in cli.reset_password(login)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AdminSession.id))) == 0
    assert admin_client.get("/api/admin/status").status_code == 401  # старый токен больше не действует
    with pytest.raises(cli.CliError, match="не найден"):
        cli.reset_password("ghost")


def _data(**extra):
    base = {
        "categories": [{"id": 1, "name": "Наука", "color": "#123456"}],
        "leaders": [{"id": 1, "name": "Иванов И.", "position": "Педагог", "contact": ""}],
        "rooms": [{"id": 1, "name": "101", "building": "А", "capacity": 20}],
        "clubs": [{"id": 1, "name": "Робототехника", "description": "", "category_id": 1, "leader_id": 1}],
        "sessions": [{"id": 1, "club_id": 1, "room_id": 1, "weekday": 1, "start_time": "10:00", "end_time": "11:00"}],
    }
    base.update(extra)
    return base


def _file(tmp_path, data):
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_seed_is_idempotent(tmp_path):
    path = _file(tmp_path, _data())
    first = cli.seed(path)
    assert first["clubs"] == {"created": 1, "existing": 0}
    second = cli.seed(path)
    assert all(v["created"] == 0 for v in second.values())
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Club.id))) == 1
        assert db.scalar(select(func.count(ClubSession.id))) == 1


def test_seed_is_atomic_on_bad_reference(tmp_path):
    data = _data(clubs=[{"id": 1, "name": "Ок", "category_id": 1, "leader_id": 1},
                        {"id": 2, "name": "Битый", "category_id": 99, "leader_id": 1}])
    with pytest.raises(cli.CliError, match="Битый"):
        cli.seed(_file(tmp_path, data))
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Club.id))) == 0  # ничего не осталось


def test_seed_rejects_overlapping_sessions(tmp_path):
    data = _data(
        clubs=[{"id": 1, "name": "А", "category_id": 1, "leader_id": 1}, {"id": 2, "name": "Б", "category_id": 1, "leader_id": 1}],
        sessions=[{"id": 1, "club_id": 1, "room_id": 1, "weekday": 1, "start_time": "10:00", "end_time": "11:00"},
                  {"id": 2, "club_id": 2, "room_id": 1, "weekday": 1, "start_time": "10:30", "end_time": "11:30"}])
    with pytest.raises(cli.CliError, match="пересекается"):
        cli.seed(_file(tmp_path, data))


def test_seed_dry_run_changes_nothing(tmp_path):
    cli.seed(_file(tmp_path, _data()), dry_run=True)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Club.id))) == 0


def test_seed_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(cli.CliError, match="JSON"):
        cli.seed(bad)


def test_backup_roundtrip_and_rotation(tmp_path):
    cli.seed(_file(tmp_path, _data()))
    for i in range(3):  # «старые» бэкапы
        (tmp_path / "bk").mkdir(exist_ok=True)
        (tmp_path / "bk" / f"clubs-2000010{i}-000000.sqlite3.gz").write_bytes(gzip.compress(b"x"))
    first = cli.backup(tmp_path / "bk", keep=2)
    second = cli.backup(tmp_path / "bk", keep=2)  # в ту же секунду: имя не должно совпасть
    assert first != second and first.exists() and second.exists()
    assert len(list((tmp_path / "bk").glob("clubs-*"))) == 2  # ротация оставила два самых свежих
    report = cli.verify_backup(second)
    assert report["integrity"] == "ok" and report["rows"]["clubs"] == 1  # revision=None: тестовая БД создана create_all, не alembic


def test_verify_backup_detects_garbage(tmp_path):
    path = tmp_path / "bad.sqlite3"
    path.write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError):
        cli.verify_backup(path)
    with pytest.raises(cli.CliError, match="не найден"):
        cli.verify_backup(tmp_path / "nope")


# ---------- server.py как процесс ----------

def run_server(*args, env=None, stdin=None):
    import os
    full = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(ROOT / "server.py"), *args], capture_output=True, text=True, cwd=ROOT,
                          env=full, input=stdin, timeout=120)


def test_server_cli_help_and_unknown_subcommand():
    out = run_server("--help")
    assert out.returncode == 0 and "build" in out.stdout and "serve" in out.stdout
    assert run_server("frobnicate").returncode == 2


def test_server_cli_build_web_and_pwa(tmp_path):
    web = run_server("build", "web", "--out", str(tmp_path / "web"))
    assert web.returncode == 0, web.stderr
    assert (tmp_path / "web" / "index.html").exists() and (tmp_path / "web" / "sw.js").exists()
    assert not (tmp_path / "web" / "tests").exists()
    assert "const BUILD_ID = 'dev'" not in (tmp_path / "web" / "sw.js").read_text(encoding="utf-8")
    ios = run_server("build", "pwa", "--out", str(tmp_path / "ios"))
    assert ios.returncode == 0, ios.stderr
    assert "Добавить" in ios.stdout or "Домой" in ios.stdout
    manifest = json.loads((tmp_path / "ios" / "manifest.webmanifest").read_text(encoding="utf-8"))
    sizes = {(i["sizes"], i.get("purpose", "any")) for i in manifest["icons"]}
    assert ("192x192", "maskable") in sizes and ("512x512", "maskable") in sizes
    assert (tmp_path / "ios" / "icons" / "apple-touch-icon.png").exists()
    html = (tmp_path / "ios" / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in html and "apple-mobile-web-app-capable" in html


def test_server_cli_ios_is_alias_of_pwa(tmp_path):
    r = run_server("build", "ios", "--out", str(tmp_path / "p"))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "p" / "manifest.webmanifest").exists()


def test_server_cli_build_back_is_self_contained_and_clean(tmp_path):
    import zipfile

    r = run_server("build", "back", "--out", str(tmp_path / "back"))
    assert r.returncode == 0, r.stderr
    pkg = tmp_path / "back" / "clubs-backend"
    for need in ("server.py", "backend/app/main.py", "backend/migrations/versions/0003_refresh_token_rotation.py",
                 "backend/requirements.lock.txt", "web/index.html", "deploy/.env.example", "RUN.md", "data/demo-data.json"):
        assert (pkg / need).exists(), need
    assert not (pkg / "backend" / "tests").exists() and not list(pkg.rglob("requirements-dev*"))
    names = zipfile.ZipFile(tmp_path / "back" / "clubs-backend.zip").namelist()
    assert not any(n.endswith((".sqlite3", ".key", "vapid_keys.json", ".env")) or "__pycache__" in n for n in names)
    assert (tmp_path / "back" / "clubs-backend.zip.sha256").read_text().strip().endswith("clubs-backend.zip")


def test_server_cli_serve_missing_frontend_is_clear_error(tmp_path):
    out = run_server("serve", "--frontend", str(tmp_path), "--no-reload")
    assert out.returncode == 2 and "index.html" in out.stderr


def test_server_cli_build_android_reports_missing_tools(tmp_path):
    # без node в PATH сборка должна падать с понятным сообщением, а не трейсбеком
    out = run_server("build", "android", "--check-only", env={"PATH": "/nonexistent", "CLUBS_TOOLCHAIN_ENV": ""})
    assert out.returncode == 1
    assert "Traceback" not in out.stderr and ("node" in out.stderr.lower() or "Node" in out.stderr)
