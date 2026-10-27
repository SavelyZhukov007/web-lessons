"""Страницы распространения: /ios, /ios/pwa, /android/, /android/download, /api/app/android."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

APK = "application/vnd.android.package-archive"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def releases(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_RELEASES_DIR", str(tmp_path))
    monkeypatch.delenv("RUSTORE_URL", raising=False)
    return tmp_path


@pytest.mark.parametrize(
    "path, marker",
    [
        ("/ios", 'data-dist-page="ios"'),
        ("/ios/pwa", 'data-dist-page="ios-pwa"'),
        ("/android/", 'data-dist-page="android"'),
    ],
)
def test_pages_html(client, path, marker):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert marker in res.text
    assert "<script>" not in res.text  # CSP script-src 'self': без инлайна


@pytest.mark.parametrize("path, target", [("/android", "/android/"), ("/ios/", "/ios")])
def test_slash_redirects(client, path, target):
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 308 and res.headers["location"] == target


def test_download_without_release_redirects_to_github(client, releases):
    res = client.get("/android/download", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "https://github.com/SavelyZhukov007/web-lessons/releases/latest/download/kipclub.apk"
    info = client.get("/api/app/android").json()
    assert info["available"] is False and info["rustore_url"] is None
    assert info["download_url"] == "https://github.com/SavelyZhukov007/web-lessons/releases/latest/download/kipclub.apk"


def test_download_missing_dir_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_RELEASES_DIR", str(tmp_path / "nope"))
    assert client.get("/android/download", follow_redirects=False).status_code == 307


def test_download_latest_by_mtime(client, releases):
    old, new = releases / "kruzhki-1.1.apk", releases / "kruzhki-1.2.apk"
    old.write_bytes(b"old")
    new.write_bytes(b"PK-new-apk")
    os.utime(old, (1_000_000, 1_000_000))
    res = client.get("/android/download")
    assert res.status_code == 200
    assert res.headers["content-type"] == APK
    assert res.headers["content-disposition"] == 'attachment; filename="kruzhki-1.2.apk"'
    assert res.content == b"PK-new-apk"
    info = client.get("/api/app/android").json()
    assert info["available"] and info["version"] == "1.2" and info["size"] == len(b"PK-new-apk")


def test_latest_json_wins_and_head(client, releases):
    (releases / "a.apk").write_bytes(b"A")
    (releases / "b.apk").write_bytes(b"BB")
    (releases / "latest.json").write_text(json.dumps({"file": "a.apk", "version": "2.0", "sha256": "ab" * 32}), encoding="utf-8")
    res = client.get("/android/download")
    assert res.content == b"A" and "a.apk" in res.headers["content-disposition"]
    assert client.head("/android/download").status_code == 200
    info = client.get("/api/app/android").json()
    assert info["version"] == "2.0" and info["sha256"] == "ab" * 32


def test_latest_json_path_traversal_ignored(client, releases, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.apk"
    outside.write_bytes(b"evil")
    (releases / "ok.apk").write_bytes(b"ok")
    (releases / "latest.json").write_text(json.dumps({"file": f"../{outside.parent.name}/evil.apk"}), encoding="utf-8")
    assert client.get("/android/download").content == b"ok"


def test_rustore_flag(client, releases, monkeypatch):
    monkeypatch.setenv("RUSTORE_URL", "https://www.rustore.ru/catalog/app/ru.kipfin.clubs")
    assert client.get("/api/app/android").json()["rustore_url"].startswith("https://www.rustore.ru/")
    monkeypatch.setenv("RUSTORE_URL", "javascript:alert(1)")
    assert client.get("/api/app/android").json()["rustore_url"] is None


def test_existing_site_untouched(client):
    assert client.get("/").status_code == 200
    assert client.get("/install").status_code == 200
    assert client.get("/api/nope").status_code == 404


# ---------- обновление внутри приложения (phase 2 F)
def test_update_manifest_fields(client, releases, monkeypatch):
    (releases / "kruzhki-1.2.apk").write_bytes(b"PK-12")
    (releases / "latest.json").write_text(
        json.dumps(
            {
                "file": "kruzhki-1.2.apk",
                "version": "1.2",
                "versionCode": 3,
                "sha256": "cd" * 32,
                "changelog": ["Новое расписание", "", "Экран загрузки"],
                "minSupported": 2,
            }
        ),
        encoding="utf-8",
    )
    res = client.get("/api/app/android")
    assert res.headers["cache-control"] == "no-cache"
    info = res.json()
    assert info["versionCode"] == 3 and info["versionName"] == "1.2" and info["version"] == "1.2"
    assert info["url"] == "/android/download" and info["size"] == 5 and info["sha256"] == "cd" * 32
    assert info["changelog"] == ["Новое расписание", "Экран загрузки"] and info["minSupported"] == 2
    monkeypatch.setenv("APP_MIN_SUPPORTED", "3")
    monkeypatch.setenv("APP_DOWNLOAD_URL", "https://cdn.example.org/kruzhki-1.2.apk")
    info = client.get("/api/app/android").json()
    assert info["minSupported"] == 3 and info["url"] == info["download_url"] == "https://cdn.example.org/kruzhki-1.2.apk"
    monkeypatch.setenv("APP_DOWNLOAD_URL", "http://insecure.example.org/a.apk")  # только https
    assert client.get("/api/app/android").json()["url"] == "/android/download"


def test_update_manifest_tolerates_bad_meta(client, releases):
    (releases / "a.apk").write_bytes(b"A")
    (releases / "latest.json").write_text(
        json.dumps({"file": "a.apk", "version": "1.0", "versionCode": "x", "changelog": "не список", "minSupported": None}),
        encoding="utf-8",
    )
    info = client.get("/api/app/android").json()
    assert info["versionCode"] is None and info["changelog"] == [] and info["minSupported"] is None


def test_update_manifest_without_release(client, releases):
    info = client.get("/api/app/android").json()
    assert info["available"] is False and info["url"] is None and "versionCode" not in info


def test_publish_release_writes_update_fields(tmp_path, monkeypatch):
    from tools.build import android as mod

    root = Path(__file__).resolve().parents[2]
    apk = tmp_path / "kruzhki-9.9.apk"
    apk.write_bytes(b"PK")
    out = tmp_path / "rel"
    mod.publish_release(apk, out)
    meta = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    ver = json.loads((root / "android" / "version.json").read_text(encoding="utf-8"))
    assert meta["versionCode"] == ver["versionCode"] and isinstance(meta["changelog"], list) and meta["minSupported"] >= 1


def test_latest_json_version_normalized(client, tmp_path, monkeypatch):
    releases = tmp_path / "rel"
    releases.mkdir()
    (releases / "a.apk").write_bytes(b"PK")
    (releases / "latest.json").write_text(json.dumps({"file": "a.apk", "version": "v1.2.890", "versionCode": 18}), encoding="utf-8")
    monkeypatch.setenv("APP_RELEASES_DIR", str(releases))
    info = client.get("/api/app/android").json()
    assert info["version"] == "1.2.890" and info["versionName"] == "v1.2.890"


def test_github_fallback_prefers_newest_including_prerelease(monkeypatch):
    from backend.app.routers import distribution as d

    d._GH_CACHE.update(at=0.0, url=None)
    monkeypatch.delenv("GITHUB_APK_URL", raising=False)
    beta = "https://github.com/x/y/releases/download/v1.2.890pb/kipclub.apk"
    releases = [{"draft": True, "assets": [{"name": "kipclub.apk", "browser_download_url": "https://draft"}]},
                {"prerelease": True, "assets": [{"name": "kipclub.apk", "browser_download_url": beta}]}]
    assert d.github_apk_url(fetch=lambda: releases) == beta
    d._GH_CACHE.update(at=0.0, url=None)

    def boom():
        raise OSError("нет сети")

    assert d.github_apk_url(fetch=boom) == d.GITHUB_APK_URL
    d._GH_CACHE.update(at=0.0, url=None)
