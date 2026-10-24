"""Регрессии из PROD_READINESS: API-01..07, SEC-07, SEC-09, QA-04."""
from datetime import date

import pytest

from .test_exception_conflicts_api import _post, add_extra_world, admin_client, get_week, make_world  # noqa: F401

MONDAY = "2026-11-02"  # понедельник
SUNDAY = "2026-11-08"


def test_api01_cyrillic_search_is_case_insensitive_and_wildcards_are_literal(admin_client):
    w = make_world(admin_client)
    admin_client.patch(f"/api/admin/clubs/{w['club']['id']}", json={"name": "Шахматы", "description": "Дебют 100% точно_"})
    for q in ("шахматы", "ШАХМАТЫ", "шах", "Шах"):
        assert [c["name"] for c in admin_client.get("/api/clubs", params={"search": q}).json()] == ["Шахматы"], q
    assert admin_client.get("/api/clubs", params={"search": "%"}).json() != []  # «%» есть в описании как литерал
    assert admin_client.get("/api/clubs", params={"search": "_"}).json() != []
    assert admin_client.get("/api/clubs", params={"search": "%%%"}).json() == []  # раньше возвращало всё
    assert admin_client.get("/api/clubs", params={"search": "x_"}).json() == []
    # поиск по расписанию тоже без ASCII-ограничения
    assert len(admin_client.get("/api/schedule", params={"week": MONDAY, "search": "ШАХМ"}).json()) == 1


def _race(admin_client, make_request, n=12):
    """Настоящая конкуренция: httpx.AsyncClient + ASGITransport, sync-эндпойнты уходят в пул потоков одновременно
    (TestClient выполняет запросы последовательно и гонку не воспроизводит)."""
    import asyncio

    import httpx

    from backend.app.main import app

    token = admin_client.post("/api/admin/login", json={"login": "admin", "password": "Password123"}).json()["access_token"]

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", headers={"Authorization": f"Bearer {token}"}) as ac:
            return await asyncio.gather(*[make_request(ac, i) for i in range(n)])

    return asyncio.run(run())


def test_api02_concurrent_conflicting_sessions_exactly_one_wins(admin_client, monkeypatch):
    import time

    from backend.app.services.schedule_conflicts import ScheduleConflictService

    real_check = ScheduleConflictService.check_proposed_state

    def slow_check(self, change):  # расширяем окно гонки между проверкой и commit — иначе на быстрой машине она не ловится
        result = real_check(self, change)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(ScheduleConflictService, "check_proposed_state", slow_check)
    w = make_world(admin_client, weekday=3, start="09:00", end="10:00")
    club2 = _post(admin_client, "/api/admin/clubs", {
        "name": "Конкурент", "description": "", "category_id": w["category"]["id"], "leader_id": w["leader"]["id"], "is_active": True,
    })
    payload = {"club_id": club2["id"], "room_id": w["room"]["id"], "weekday": 1, "start_time": "12:00", "end_time": "13:00"}

    async def attempt(ac, _):
        return (await ac.post("/api/admin/sessions", json=payload)).status_code

    codes = _race(admin_client, attempt)
    assert sorted(codes) == [201] + [409] * 11, codes
    monday = [e for e in get_week(admin_client, MONDAY) if e["date"] == MONDAY and e["room_id"] == w["room"]["id"] and e["club_id"] == club2["id"]]
    assert len(monday) == 1


def test_api03_patch_cancellation_runs_conflict_check(admin_client):
    a = make_world(admin_client, weekday=1, start="11:00", end="12:00")
    cancel = _post(admin_client, "/api/admin/exceptions/cancellations", {
        "session_id": a["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": "",
    })
    b = add_extra_world(admin_client, weekday=2, start="11:00", end="12:00", room_id=a["room"]["id"], name="B")
    _post(admin_client, "/api/admin/exceptions/moves", {
        "session_id": b["session"]["id"], "original_date": "2026-11-03", "type": "moved",
        "new_date": MONDAY, "new_start_time": "11:00", "new_end_time": "12:00", "new_room_id": a["room"]["id"], "comment": "",
    })
    # сдвигаем отмену на другую неделю → A вернулся бы на MONDAY поверх B
    r = admin_client.patch(f"/api/admin/exceptions/{cancel['id']}", json={"original_date": "2026-11-09"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "CONFLICT"
    still = [e for e in get_week(admin_client, MONDAY) if e["session_id"] == a["session"]["id"] and e["date"] == MONDAY]
    assert still and still[0]["status"] == "cancelled"  # состояние не изменилось


def test_api04_original_date_must_match_session_weekday(admin_client):
    w = make_world(admin_client, weekday=1)
    bad_date = "2026-11-03"  # вторник
    r = admin_client.post("/api/admin/exceptions/cancellations", json={
        "session_id": w["session"]["id"], "original_date": bad_date, "type": "cancelled", "comment": ""})
    assert r.status_code == 422 and "вторник" in r.json()["detail"]
    r = admin_client.post("/api/admin/exceptions/moves", json={
        "session_id": w["session"]["id"], "original_date": bad_date, "type": "moved", "new_date": "2026-11-04",
        "new_start_time": "10:00", "new_end_time": "11:00", "new_room_id": w["room"]["id"], "comment": ""})
    assert r.status_code == 422
    assert admin_client.get("/api/admin/exceptions").json() == []


def test_api04_move_to_sunday_rejected(admin_client):
    w = make_world(admin_client, weekday=1)
    r = admin_client.post("/api/admin/exceptions/moves", json={
        "session_id": w["session"]["id"], "original_date": MONDAY, "type": "moved", "new_date": SUNDAY,
        "new_start_time": "10:00", "new_end_time": "11:00", "new_room_id": w["room"]["id"], "comment": ""})
    assert r.status_code == 422 and "воскресенье" in r.json()["detail"]


def test_api04_patch_exception_original_date_weekday_checked(admin_client):
    w = make_world(admin_client, weekday=1)
    c = _post(admin_client, "/api/admin/exceptions/cancellations", {
        "session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": ""})
    r = admin_client.patch(f"/api/admin/exceptions/{c['id']}", json={"original_date": "2026-11-04"})
    assert r.status_code == 422
    ok = admin_client.patch(f"/api/admin/exceptions/{c['id']}", json={"comment": "праздник"})
    assert ok.status_code == 200 and ok.json()["comment"] == "праздник"


def test_api04_weekday_change_blocked_when_exceptions_exist(admin_client):
    w = make_world(admin_client, weekday=1)
    _post(admin_client, "/api/admin/exceptions/cancellations", {
        "session_id": w["session"]["id"], "original_date": MONDAY, "type": "cancelled", "comment": ""})
    r = admin_client.patch(f"/api/admin/sessions/{w['session']['id']}", json={"weekday": 2})
    assert r.status_code == 409 and "отмены/переносы" in r.json()["detail"]
    # без исключений — можно
    w2 = add_extra_world(admin_client, weekday=4, start="14:00", end="15:00", name="Free")
    assert admin_client.patch(f"/api/admin/sessions/{w2['session']['id']}", json={"weekday": 5}).status_code == 200


@pytest.mark.parametrize("value", ["20261102", "2026-W45-1", "2026-11-2", "２０２６-11-02", "9999-12-27", "1999-12-27", "0001-01-01"])
def test_api05_06_week_strict_format_and_range(client, value):
    assert client.get("/api/schedule", params={"week": value}).status_code == 422


def test_api05_ics_extreme_week_422(client, admin_client):
    w = make_world(admin_client)
    r = admin_client.get(f"/api/clubs/{w['club']['id']}/calendar.ics", params={"week": "9999-12-27"})
    assert r.status_code == 422


def test_api07_today_msk_uses_moscow_time(monkeypatch):
    from datetime import datetime, timezone

    from backend.app.services import clock

    fixed = datetime(2026, 11, 1, 22, 30, tzinfo=timezone.utc)  # в Москве уже 2 ноября 01:30

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(clock, "datetime", FakeDT)
    assert clock.today_msk() == date(2026, 11, 2)


def test_sec07_public_leaders_hide_contacts_and_inactive(admin_client):
    w = make_world(admin_client)
    hidden = _post(admin_client, "/api/admin/leaders", {"name": "Без кружка", "position": "", "contact": "secret@test"})
    leaders = admin_client.get("/api/leaders").json()
    assert [l["id"] for l in leaders] == [w["leader"]["id"]]
    assert "contact" not in leaders[0]
    assert hidden["id"] not in [l["id"] for l in leaders]
    # карточка активного кружка контакт по-прежнему отдаёт (PUB-01)
    assert admin_client.get(f"/api/clubs/{w['club']['id']}").json()["leader"]["contact"] == "ivan@test.local"
    # админ видит всё
    assert all("contact" in l for l in admin_client.get("/api/admin/leaders").json())


def test_sec09_field_length_limits(admin_client):
    w = make_world(admin_client)
    assert admin_client.post("/api/admin/categories", json={"name": "x" * 121, "color": "#112233"}).status_code == 422
    assert admin_client.post("/api/admin/leaders", json={"name": "n", "position": "p" * 301, "contact": ""}).status_code == 422
    assert admin_client.post("/api/admin/clubs", json={
        "name": "n", "description": "d" * 4001, "category_id": w["category"]["id"], "leader_id": w["leader"]["id"]}).status_code == 422
    assert admin_client.post("/api/admin/login", json={"login": "a", "password": "p" * 256}).status_code == 422


def test_qa04_parallel_writes_do_not_hit_database_is_locked(admin_client):
    async def create(ac, i):
        return (await ac.post("/api/admin/rooms", json={"name": f"R{i}", "building": "B", "capacity": 10})).status_code

    assert set(_race(admin_client, create, n=36)) == {201}
