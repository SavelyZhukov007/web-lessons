from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import SiteFiles
from tools.build.assets import fingerprint_assets


def source(path: Path):
    (path / "js").mkdir(parents=True)
    (path / "css").mkdir()
    (path / "index.html").write_text('<html><head><link href="/css/main.css"></head><script src="/js/main.js"></script></html>')
    (path / "js/main.js").write_text("import './lazy.js'; const css='/css/main.css';")
    (path / "js/lazy.js").write_text("export const value=1;")
    (path / "css/main.css").write_text("html{color:red}")


def test_immutable_graph_retains_relative_imports_and_versions_absolute_paths(tmp_path):
    source(tmp_path)
    version = fingerprint_assets(tmp_path)
    assert len(version) == 20
    root = tmp_path / "assets" / version
    assert "import './lazy.js'" in (root / "js/main.js").read_text()
    assert (root / "js/lazy.js").exists()
    assert f"/assets/{version}/css/main.css" in (root / "js/main.js").read_text()
    assert f"/assets/{version}/js/main.js" in (tmp_path / "index.html").read_text()


def test_source_change_gets_new_url(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    source(first)
    source(second)
    (second / "css/main.css").write_text("html{color:blue}")
    assert fingerprint_assets(first) != fingerprint_assets(second)


def test_only_fingerprinted_paths_are_immutable(tmp_path):
    source(tmp_path)
    version = fingerprint_assets(tmp_path)
    app = FastAPI()
    app.mount("/", SiteFiles(directory=tmp_path, html=True))
    with TestClient(app) as client:
        response = client.get(f"/assets/{version}/js/main.js")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/js/main.js").headers["cache-control"] == "no-cache"
        assert client.get("/").headers["cache-control"] == "no-cache"
