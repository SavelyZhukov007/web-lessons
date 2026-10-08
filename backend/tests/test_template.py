"""Проверки только готовой инфраструктуры. Бизнес-функции пока заглушки."""
from fastapi.testclient import TestClient
from backend.app.main import app

def test_template_routes():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        for path in ["/", "/clubs.html", "/club.html", "/admin/login.html", "/admin/index.html", "/js/api.js", "/css/common.css"]:
            assert client.get(path).status_code == 200
        assert client.get("/api/clubs").status_code == 501
        assert client.get("/api/admin/status").status_code == 401
        assert client.get("/api/unknown").status_code == 404
        assert client.get("/README.md").status_code == 404
