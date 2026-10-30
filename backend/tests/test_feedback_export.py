"""tools/feedback_export.py: сравнение по id/sha256, скачивание только нового, проверка хэшей, хранение всего локально
при ротации на сервере. «Сервер» — локальная папка (LocalRunner) и подставные ssh/docker (проверка команд и кавычек)."""
import csv
import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services import feedback as svc

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import feedback_export as fx  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def server(tmp_path, monkeypatch):
    d = tmp_path / "server" / "feedback"
    monkeypatch.setenv("FEEDBACK_DIR", str(d))
    monkeypatch.setenv("FEEDBACK_KEEP", "3")
    return d


def add(n: int, start: int = 0) -> list[str]:
    data = svc.validate({"type": "bug", "description": "Не грузится расписание", "contact": "@qa_team"}, [PNG])
    return [svc.save(data, now=T0 + timedelta(minutes=start + i))["id"] for i in range(n)]


def run(server, out, *extra):
    return fx.main(["--server", "test", "--local-remote", str(server), "--out", str(out), *extra])


def index(out):
    with (out / "test" / "index.csv").open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_download_new_then_nothing(server, tmp_path, capsys):
    out = tmp_path / "QA"
    ids = add(2)
    assert run(server, out) == 0
    rows = index(out)
    assert [r["id"] for r in rows] == ids and all(r["on_server"] == "yes" for r in rows)
    folder = out / "test" / rows[0]["folder"]
    assert (folder / "screenshots" / "01.png").read_bytes() == PNG and (folder / "manifest.json").is_file()
    assert "test/" in (out / "README.md").read_text(encoding="utf-8")
    capsys.readouterr()
    assert run(server, out) == 0
    assert "новых: 0, изменённых: 0, без изменений: 2" in capsys.readouterr().out


def test_retention_on_server_local_keeps_everything(server, tmp_path):
    out = tmp_path / "QA"
    first = add(3)
    run(server, out)
    later = add(2, start=10)  # сервер держит 3 → два старых удалены
    assert len(svc.complete_folders(server)) == 3
    run(server, out)
    rows = index(out)
    assert [r["id"] for r in rows] == first + later
    assert {r["id"]: r["on_server"] for r in rows} == {**{i: "no" for i in first[:2]}, **{i: "yes" for i in first[2:] + later}}
    assert len(list(server.iterdir())) == 3  # на сервере ничего не тронуто


def test_dry_run_writes_nothing(server, tmp_path, capsys):
    add(1)
    assert run(server, tmp_path / "QA", "--dry-run") == 0
    assert "would download" in capsys.readouterr().out and not (tmp_path / "QA").exists()


def test_changed_and_corrupted_local_are_redownloaded(server, tmp_path, capsys):
    out = tmp_path / "QA"
    add(2)
    run(server, out)
    a, b = sorted(p for p in (out / "test").iterdir() if p.is_dir() and not p.name.startswith("."))
    (a / "logs.json").write_text("[]tampered", encoding="utf-8")  # локальная порча
    srv_b = server / b.name  # отчёт изменился на сервере (новый manifest)
    (srv_b / "description.md").write_text("# new\n\nИсправленное описание\n", encoding="utf-8")
    m = svc.build_manifest(srv_b, json.loads((srv_b / "manifest.json").read_text())["id"], "x", b.name)
    (srv_b / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    capsys.readouterr()
    assert run(server, out) == 0
    assert "изменённых: 2" in capsys.readouterr().out
    assert fx.verify(a, json.loads((a / "manifest.json").read_text())) == []
    assert "Исправленное" in (b / "description.md").read_text(encoding="utf-8")
    assert len(list((out / "test" / ".replaced").iterdir())) == 2


def test_hash_mismatch_from_server_is_rejected(server, tmp_path, capsys):
    add(1)
    folder = next(server.iterdir())
    (folder / "logs.json").write_text('["changed after manifest"]', encoding="utf-8")
    assert run(server, tmp_path / "QA") == 1
    assert "не сошлось" in capsys.readouterr().out
    assert fx.local_reports(tmp_path / "QA" / "test") == {}


def test_tmp_and_incomplete_folders_ignored(server, tmp_path):
    add(1)
    (server / ".tmp-x").mkdir()
    (server / "2026-01-01_000000_bug_nomanifs").mkdir()
    run(server, tmp_path / "QA")
    assert len(index(tmp_path / "QA")) == 1


def test_extract_rejects_path_traversal(tmp_path):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(fx.ExportError):
        fx.extract(buf.getvalue(), tmp_path, {"a"})


def _script(path: Path, body: str):
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.mark.skipif(os.name == "nt", reason="shell-заглушки")
def test_system_ssh_and_docker_exec_mode(server, tmp_path, monkeypatch, capsys):
    """Без paramiko: системный ssh + docker compose exec (заглушки выполняют команду локально)."""
    add(2)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls.log"
    # ssh … user@host "<команда>" → выполнить последнюю строку через sh
    _script(bin_ / "ssh", f'echo "ssh $*" >> {log}\nfor last; do :; done\nexec sh -c "$last"\n')
    # docker compose -f F exec -T app CMD… → выполнить CMD, подменив /data/feedback на папку «тома»
    _script(bin_ / "docker", f'echo "docker $*" >> {log}\nshift 5\n[ "$1" = "app" ] || exit 9\nshift\n'
            f'cmd="$1"; shift\nfor a; do set -- "$@" "$(printf %s "$a" | sed "s#^/data/feedback#{server}#")"; shift; done\n'
            f'[ "$cmd" = python3 ] && cmd={sys.executable}\nexec "$cmd" "$@"\n')
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setitem(sys.modules, "paramiko", None)  # «paramiko не установлен»
    out = tmp_path / "QA"
    assert fx.main(["--server", "test", "--key", "/k/id", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "через ssh" in text and "(docker" in text and len(index(out)) == 2
    calls = log.read_text()
    assert "-i /k/id savely-server@185.53.233.170" in calls and "-p 22" in calls
    assert "docker compose -f /opt/clubs/docker-compose.yml exec -T app tar -C /data/feedback -cf -" in calls
    assert "rm " not in calls
