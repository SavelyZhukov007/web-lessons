"""SEC-04/05/08/09/14, API-08/09/11: заголовки, CSRF, health, скрытая статика, gzip, 404-страница."""

from backend.app import settings

from .helpers import login, make_admin


def test_security_headers_and_csp(client):
    r = client.get("/")
    h = r.headers
    assert "script-src 'self'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] and h["x-request-id"]
    api = client.get("/api/admin/status")
    assert api.headers["cache-control"] == "no-store"
    assert client.get("/admin/login.html").headers["cache-control"] == "no-store"


def test_request_id_is_propagated(client):
    assert client.get("/healthz", headers={"X-Request-ID": "abc123"}).headers["x-request-id"] == "abc123"


def test_csrf_blocks_cross_origin_cookie_writes(client):
    make_admin()
    assert login(client).status_code == 200
    evil = {"Origin": "https://evil.example"}
    r = client.post("/api/admin/categories", json={"name": "x", "color": "#112233"}, headers=evil)
    assert r.status_code == 403
    same = {"Origin": "http://testserver"}
    r = client.post("/api/admin/categories", json={"name": "x", "color": "#112233"}, headers=same)
    assert r.status_code == 201
    r = client.post("/api/admin/categories", json={"name": "y", "color": "#112233"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_csrf_trusted_origin_and_bearer_are_allowed(client, monkeypatch):
    make_admin()
    token = login(client).json()["access_token"]
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://admin.college.ru")
    ok = client.post("/api/admin/categories", json={"name": "a", "color": "#112233"}, headers={"Origin": "https://admin.college.ru"})
    assert ok.status_code == 201
    # Bearer: cookie не используется → CSRF неприменим (мобильное приложение с Origin http://localhost)
    client.cookies.clear()
    r = client.post(
        "/api/admin/categories",
        json={"name": "b", "color": "#112233"},
        headers={"Origin": "http://localhost", "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


def test_health_and_readiness(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    # тесты работают на create_all без alembic_version → «migration-pending» допустим, но БД отвечает
    assert ready.status_code in (200, 503)
    assert ready.json()["status"] in ("ready", "migration-pending")


def test_readyz_503_when_db_unavailable(client, monkeypatch):
    from backend.app import main

    class Boom:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(main, "SessionLocal", lambda: Boom())
    assert client.get("/readyz").status_code == 503


def test_internal_files_not_served(client):
    assert client.get("/mock-data.json").status_code == 404
    assert client.get("/tests/schedule-dates.test.mjs").status_code == 404
    assert client.get("/css/campus.css").status_code == 200


def test_html_404_for_pages_json_for_api(client):
    page = client.get("/nope.html")
    assert page.status_code == 404 and "text/html" in page.headers["content-type"]
    api = client.get("/api/nope")
    assert api.status_code == 404 and api.json() == {"detail": "API-маршрут не найден"}


def test_gzip_and_cache_headers(client):
    r = client.get("/css/schedule.css", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    assert client.get("/css/schedule.css").headers["cache-control"] == "no-cache"
    font = client.get("/fonts/GolosText-Variable.woff2", headers={"Accept-Encoding": "gzip"})
    assert "max-age" in font.headers["cache-control"]


def test_docs_disabled_in_production_default(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert settings.docs_enabled() is False
    monkeypatch.setenv("ENV", "development")
    assert settings.docs_enabled() is True
