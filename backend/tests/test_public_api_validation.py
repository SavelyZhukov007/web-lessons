"""Публичный API: проверка входных данных и крайние случаи (неделя, диапазоны, периоды, 404)."""
import pytest

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401


@pytest.mark.parametrize("week,msg", [
    ("2026-13-01", "формат"),
    ("1999-01-04", "диапазон"),
    ("2026-11-10", "понедельник"),
    ("26-11-09", "формат"),
])
def test_week_param_validation(client, week, msg):
    for url in ("/api/schedule", "/api/week", "/api/periods/week"):
        r = client.get(url, params={"week": week})
        assert r.status_code == 422 and msg in r.json()["detail"], (url, r.text)


def test_periods_week_active_upcoming_ended(admin_client):  # noqa: F811
    _post(admin_client, "/api/admin/periods", {"name": "Осень", "start_date": "2026-09-01",
                                               "end_date": "2026-12-27", "even_week_start": "2026-08-31"})
    active = admin_client.get("/api/periods/week", params={"week": "2026-11-09"}).json()
    assert active[0]["status"] == "active" and active[0]["parity"] in {"even", "odd"}
    before = admin_client.get("/api/periods/week", params={"week": "2026-08-03"}).json()
    assert before[0]["status"] == "upcoming"
    after = admin_client.get("/api/periods/week", params={"week": "2027-02-01"}).json()
    assert after[0]["status"] == "ended"


def test_periods_week_without_periods(client):
    assert client.get("/api/periods/week", params={"week": "2026-11-09"}).json() == []


def test_public_lists_and_filters(admin_client):  # noqa: F811
    w = make_world(admin_client)
    assert any(r["id"] == w["room"]["id"] for r in admin_client.get("/api/rooms").json())
    assert admin_client.get("/api/leaders").status_code == 200
    clubs = admin_client.get("/api/clubs", params={"category_id": w["category"]["id"], "search": w["club"]["name"][:3]}).json()
    assert [c["id"] for c in clubs] == [w["club"]["id"]]
    assert admin_client.get("/api/clubs", params={"search": "нет-такого"}).json() == []
    assert admin_client.get("/api/clubs/999999").status_code == 404
    sched = admin_client.get("/api/schedule", params={"week": "2026-11-09", "leader_id": w["leader"]["id"],
                                                       "room_id": w["room"]["id"], "category_id": w["category"]["id"],
                                                       "search": w["club"]["name"]}).json()
    assert len(sched) == 1
    assert admin_client.get("/api/schedule", params={"week": "2026-11-09", "room_id": 999999}).json() == []


def test_club_calendar_and_occurrence_errors(admin_client):  # noqa: F811
    w = make_world(admin_client)
    cid, sid = w["club"]["id"], w["session"]["id"]
    base = f"/api/clubs/{cid}/calendar.ics"
    assert admin_client.get(base, params={"week": "2026-11-09", "start": "2026-11-09"}).status_code == 422
    assert admin_client.get("/api/clubs/999999/calendar.ics", params={"week": "2026-11-09"}).status_code == 404
    assert admin_client.get("/api/clubs/999999/calendar.ics").status_code == 404
    assert admin_client.get(base, params={"start": "2026-11-09"}).status_code == 422
    assert admin_client.get(base, params={"start": "2026-11-20", "end": "2026-11-09"}).status_code == 422
    assert admin_client.get(base, params={"start": "2026-01-01", "end": "2026-12-31"}).status_code == 422
    assert admin_client.get(base, params={"start": "2026-11-09", "end": "2026-11-30"}).status_code == 200
    occ = f"/api/clubs/{cid}/occurrences"
    assert admin_client.get("/api/clubs/999999/occurrences").status_code == 404
    assert admin_client.get(occ, params={"from": "2026-11-30", "to": "2026-11-01"}).status_code == 422
    assert admin_client.get(occ, params={"from": "2026-01-01", "to": "2027-12-31"}).status_code == 422
    assert admin_client.get(occ, params={"from": "2026-11-01", "to": "2026-11-30"}).status_code == 200
    assert admin_client.get("/api/sessions/999999/occurrences").status_code == 404
    assert admin_client.get(f"/api/sessions/{sid}/occurrences", params={"from": "2026-11-01", "to": "2026-11-30"}).status_code == 200
