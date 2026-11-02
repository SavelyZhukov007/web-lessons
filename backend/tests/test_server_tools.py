"""tools/check_server.py и tools/db_summary.py: адреса с префиксом пути, коды выхода, ошибки БД."""
import sqlite3
import urllib.error

import pytest

from tools import check_server, db_summary


class _Resp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(statuses, seen):
    def open_(req, timeout):
        seen.append(req.full_url)
        st = statuses.get(req.full_url, 200)
        if isinstance(st, BaseException):
            raise st
        if st >= 400:
            raise urllib.error.HTTPError(req.full_url, st, "x", {}, None)
        return _Resp(st)
    return open_


@pytest.mark.parametrize("base,expected", [
    ("http://h", "http://h/healthz"),
    ("http://h/", "http://h/healthz"),
    ("http://h/clubs", "http://h/clubs/healthz"),
    ("http://h/clubs/", "http://h/clubs/healthz"),
])
def test_endpoint_url_keeps_path_prefix(base, expected):
    assert check_server.endpoint_url(base, "/healthz") == expected


def test_check_server_ok_with_prefix(capsys):
    seen = []
    assert check_server.main(["https://x.ru/clubs"], opener=_opener({}, seen)) == 0
    assert seen == ["https://x.ru/clubs/healthz", "https://x.ru/clubs/readyz"]
    assert "application is ready" in capsys.readouterr().out


@pytest.mark.parametrize("err,msg", [
    (503, "status 503"),
    (TimeoutError(), "timeout"),
    (urllib.error.URLError(TimeoutError()), "timeout"),
    (urllib.error.URLError("refused"), "connection failed"),
])
def test_check_server_failures(err, msg, capsys):
    rc = check_server.main(["http://h"], opener=_opener({"http://h/readyz": err}, []))
    out = capsys.readouterr().out
    assert rc == 1 and "OK: /healthz" in out and msg in out and "Check failed" in out


def test_check_server_usage(capsys):
    assert check_server.main([]) == 1
    assert "Usage" in capsys.readouterr().out


def _make_db(path):
    conn = sqlite3.connect(path)
    for t in ("categories", "leaders", "rooms", "sessions", "session_exceptions"):
        conn.execute(f"CREATE TABLE {t} (id INTEGER)")
    conn.execute("CREATE TABLE clubs (id INTEGER, is_active INTEGER)")
    conn.executemany("INSERT INTO clubs VALUES (?, ?)", [(1, 1), (2, 1), (3, 0)])
    conn.execute("INSERT INTO rooms VALUES (1)")
    conn.commit()
    conn.close()


def test_db_summary_ok(tmp_path, capsys):
    db = tmp_path / "c.db"
    _make_db(db)
    res = db_summary.get_db_summary(str(db))
    assert res["active_clubs"] == 2 and res["non_active_clubs"] == 1 and res["rooms"] == 1
    assert db_summary.main(["-p", str(db)]) == 0
    assert "Сводка" in capsys.readouterr().out


def test_db_summary_missing_file_exits_nonzero(tmp_path, capsys):
    assert db_summary.main(["-p", str(tmp_path / "none.db")]) == 1
    assert "не найдена" in capsys.readouterr().err


def test_db_summary_sqlite_error_exits_nonzero(tmp_path, capsys):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    assert db_summary.get_db_summary(str(db)) is None
    assert db_summary.main(["-p", str(db)]) == 1
    assert "Ошибка при работе с бд" in capsys.readouterr().err
