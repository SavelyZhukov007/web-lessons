"""«Обратная связь»: приём отчёта (скриншоты + логи), проверки, MIME, частота, manifest, атомарная запись, хранение последних N."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services import feedback as svc

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def fb_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDBACK_DIR", str(tmp_path / "feedback"))
    svc.reset_limits()
    yield tmp_path / "feedback"
    svc.reset_limits()


def send(client, shots=(), **over):
    data = {"type": "bug", "description": "Не открывается расписание на телефоне", "contact": "@tester",
            "meta": json.dumps({"version": "v1.7.829ibW", "platform": "W", "userAgent": "UA"}),
            "logs": json.dumps([{"level": "error", "msg": "boom token=abc123secret"}])}
    data.update(over)
    files = [("screenshots", (f"s{i}.png", b, "image/png")) for i, b in enumerate(shots)]
    return client.post("/api/feedback", data=data, files=files or None)


def test_create_with_screenshots_and_logs(client, fb_dir):
    r = send(client, [PNG, JPG])
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    [folder] = list(fb_dir.iterdir())
    assert str(uuid.UUID(fid)) == fid and folder.name.endswith(f"_bug_{fid[:8]}")
    rep = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    assert rep["id"] == fid and rep["platform"] == "W" and rep["app_version"] == "v1.7.829ibW"
    assert rep["server"]["env"] == "test" and rep["contact"] == "@tester"
    assert sorted(p.name for p in (folder / "screenshots").iterdir()) == ["01.png", "02.jpg"]
    assert "Не открывается" in (folder / "description.md").read_text(encoding="utf-8")
    logs = (folder / "logs.json").read_text(encoding="utf-8")
    assert "boom" in logs and "abc123secret" not in logs


@pytest.mark.parametrize("over,code", [
    ({"type": "spam"}, 422), ({"description": "short"}, 422), ({"description": "x" * 2001}, 422),
    ({"contact": "not a contact!"}, 422), ({"logs": "{bad"}, 422),
])
def test_validation(client, over, code):
    assert send(client, **over).status_code == code


def test_too_many_screenshots_and_size(client):
    assert send(client, [PNG] * 6).status_code == 422
    assert send(client, [PNG + b"\x00" * (5 * 1024 * 1024)]).status_code == 413


def test_mime_by_magic_bytes(client, fb_dir):
    r = send(client, [b"GIF89a" + b"\x00" * 20])
    assert r.status_code == 415
    r = send(client, [b"<?php echo 1; ?>"])
    assert r.status_code == 415
    assert not fb_dir.exists() or not any(fb_dir.iterdir())


def test_honeypot_is_silently_dropped(client, fb_dir):
    r = send(client, website="http://spam")
    assert r.status_code == 201 and "id" not in r.json()
    assert not fb_dir.exists() or not any(fb_dir.iterdir())


def test_rate_limit(client):
    for _ in range(5):
        assert send(client).status_code == 201
    r = send(client)
    assert r.status_code == 429 and r.headers.get("retry-after") == "3600"


def test_manifest_hashes_and_sizes(client, fb_dir):
    fid = send(client, [PNG, JPG]).json()["id"]
    folder = next(fb_dir.iterdir())
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert m["id"] == fid and m["folder"] == folder.name and m["created_at"].startswith(folder.name[:10])
    assert set(m["files"]) == {"report.json", "description.md", "logs.json", "screenshots/01.png", "screenshots/02.jpg"}
    for rel, info in m["files"].items():
        data = (folder / rel).read_bytes()
        assert info == {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def test_no_admin_endpoints(client):
    for path in ("/api/admin/feedback", "/api/admin/feedback/1", "/api/admin/feedback/export"):
        assert client.get(path).status_code in (401, 404, 405)
    assert client.get("/api/feedback").status_code in (404, 405)


def test_retention_keeps_last_n(fb_dir, monkeypatch):
    monkeypatch.setenv("FEEDBACK_KEEP", "3")
    t0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    data = svc.validate({"type": "idea", "description": "Сделайте тёмную тему"}, [])
    ids = [svc.save(data, now=t0 + timedelta(minutes=i))["id"] for i in range(5)]
    left = sorted(p.name for p in fb_dir.iterdir())
    assert len(left) == 3 and [n[-8:] for n in left] == [i[:8] for i in ids[2:]]
    monkeypatch.setenv("FEEDBACK_KEEP", "bad")
    assert svc.settings.feedback_keep() == 50


def test_atomic_write_and_tmp_handling(fb_dir, monkeypatch):
    monkeypatch.setenv("FEEDBACK_KEEP", "1")
    fb_dir.mkdir(parents=True)
    fresh = fb_dir / ".tmp-inprogress"
    fresh.mkdir()
    stale = fb_dir / ".tmp-crashed"
    stale.mkdir()
    import os
    os.utime(stale, (0, 0))
    incomplete = fb_dir / "2000-01-01_000000_bug_deadbeef"  # без manifest — не трогаем и не считаем
    incomplete.mkdir()
    data = svc.validate({"type": "bug", "description": "Ошибка при сохранении"}, [PNG])
    real = svc.save.__globals__["build_manifest"]
    monkeypatch.setitem(svc.save.__globals__, "build_manifest", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        svc.save(data)
    assert {p.name for p in fb_dir.iterdir()} == {".tmp-inprogress", ".tmp-crashed", incomplete.name}  # сбой — временная папка удалена
    monkeypatch.setitem(svc.save.__globals__, "build_manifest", real)
    svc.save(data)
    svc.save(data)
    names = {p.name for p in fb_dir.iterdir()}
    assert ".tmp-crashed" not in names and ".tmp-inprogress" in names and incomplete.name in names
    assert len([p for p in svc.complete_folders(fb_dir)]) == 1


def test_logs_optional_server_side(client, fb_dir):
    r = send(client, logs="")
    assert r.status_code == 201
    folder = next(fb_dir.iterdir())
    assert json.loads((folder / "logs.json").read_text(encoding="utf-8")) == []
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["logs_attached"] is False


def test_rating_and_source_saved(client, fb_dir):
    r = send(client, rating="4", source="prompt_update", contact="")
    assert r.status_code == 201, r.text
    [folder] = list(fb_dir.iterdir())
    rep = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    assert rep["rating"] == 4 and rep["source"] == "prompt_update" and rep["contact"] is None


@pytest.mark.parametrize("rating", ["0", "6", "5.5", "отлично"])
def test_rating_out_of_range_rejected(client, rating):
    r = send(client, rating=rating)
    assert r.status_code == 422 and r.json()["detail"] == "Оценка от 1 до 5"


def test_defaults_without_rating_and_unknown_source(client, fb_dir):
    assert send(client).status_code == 201
    assert send(client, source="<script>").status_code == 201
    reports = sorted((json.loads((f / "report.json").read_text(encoding="utf-8")) for f in fb_dir.iterdir()), key=lambda r: r["source"])
    assert [(r["rating"], r["source"]) for r in reports] == [(None, "other"), (None, "settings")]


def test_user_agent_trimmed_and_device_name_dropped(client, fb_dir):
    ua = "Mozilla/5.0 (Linux; Android 14; TECNO BF7n Build/UP1A.231005.007; wv) AppleWebKit/537.36 Version/4.0 Chrome/131.0.6778.39 Mobile Safari/537.36"
    meta = {"version": "v1.9.024ibA", "platform": "A", "userAgent": ua,
            "device": {"name": "Телефон Савелия", "model": "TECNO BF7n", "manufacturer": "TECNO", "osVersion": "14",
                       "platform": "android", "webViewVersion": "131.0.6778.39", "memUsed": 1}}
    assert send(client, meta=json.dumps(meta, ensure_ascii=False)).status_code == 201
    [folder] = list(fb_dir.iterdir())
    client_meta = json.loads((folder / "report.json").read_text(encoding="utf-8"))["client"]
    assert client_meta["ua"] == "Android 14 · WebView 131" and "userAgent" not in client_meta
    assert client_meta["device"] == {"model": "TECNO BF7n", "manufacturer": "TECNO", "osVersion": "14", "platform": "android", "webViewMajor": 131}
    assert "Савелия" not in (folder / "report.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("ua, short", [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1", "iOS 17 · Safari 17"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 YaBrowser/24.10.0.0 Safari/537.36", "Windows 10.0 · Яндекс Браузер 24"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0", "Linux · Firefox 132"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36 Edg/131.0", "macOS 10 · Edge 131"),
    ("curl/8.0", ""),
])
def test_short_ua(ua, short):
    assert svc.short_ua(ua) == short


def test_texts_use_ty_without_long_dashes(client):
    texts = [send(client, type="spam").json()["detail"], send(client, description="short").json()["detail"]]
    assert texts == ["Выбери тип сообщения", "Напиши чуть подробнее, хотя бы 10 символов"]
    for _ in range(svc.RATE):
        send(client)
    limited = send(client)
    assert limited.status_code == 429 and limited.json()["detail"] == "Слишком много сообщений. Попробуй через час."
    assert all("—" not in t for t in texts)
