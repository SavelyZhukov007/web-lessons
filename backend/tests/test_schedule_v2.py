"""schedule v2: occurrence_source, движок конфликтов, .ics, уведомления, публикация импорта."""
from __future__ import annotations

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from backend.app.database import SessionLocal, engine as db_engine
from backend.app.services import calendar_export, import_publish
from backend.app.services import conflicts as ce
from backend.app.services import occurrence_source as occ
from backend.app.services.schedule import build_week

from .test_exception_conflicts_api import _post, add_extra_world, admin_client, make_world  # noqa: F401

TODAY = date(2026, 10, 27)  # вторник


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(occ, "today_msk", lambda: TODAY)
    monkeypatch.setenv("CLUBS_BACKUP_DIR", str(tmp_path / "backups"))
    path = tmp_path / "overrides.json"
    monkeypatch.setattr(ce.ConflictOverrides, "__init__", lambda self, p=None: setattr(self, "path", p or path))
    occ.set_provider(None)
    yield
    occ.set_provider(None)
    with db_engine.begin() as conn:
        for t in ("session_leaders", "club_leaders", "session_rooms", "no_class_days"):
            conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text("UPDATE sessions SET period_id = NULL"))
        conn.execute(text("DELETE FROM academic_periods"))


class FakeCalendar(occ.FallbackCalendar):
    pass


class FakeProvider:
    """Имитация T1: периоды, чётность, неучебные дни, repeat из атрибута сессии."""

    name = "fake-t1"

    def __init__(self, calendar, repeats):
        self.calendar = calendar
        self.repeats = repeats

    def load_calendar(self, db):
        return self.calendar

    def session_dates(self, session, date_from, date_to, calendar):
        clone = type("S", (), dict(vars(session)))()
        clone.repeat = self.repeats.get(session.id, getattr(session, "repeat", None))
        return occ._FallbackProvider.session_dates(clone, date_from, date_to, calendar)


def autumn_calendar(no_class=None):
    return FakeCalendar(
        periods=[occ.Period(1, "Осень 2026", date(2026, 9, 1), date(2027, 1, 10), date(2026, 8, 31), "odd")],
        no_class=no_class or {},
    )


def snap():
    with SessionLocal() as db:
        return occ.load_snapshot(db)


# ------------------------------------------------------------------ адаптер / fallback


def test_t1_provider_is_used():
    """Базовые даты берутся из services.occurrences.original_occurs (T1)."""
    assert occ.provider_name() == "occurrences"
    occ.set_provider(occ._FallbackProvider)
    assert occ.provider_name() == "fallback"


def test_fallback_weekly_and_one_off(admin_client):
    w = make_world(admin_client, weekday=1)
    s = snap()
    dates = [o.date for o in occ.snapshot_occurrences(s, date(2026, 11, 1), date(2026, 11, 30))]
    assert dates == [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 30)]
    one = _post(admin_client, "/api/admin/sessions", {
        "club_id": w["club"]["id"], "room_id": w["room"]["id"], "weekday": 3,
        "start_time": "15:00", "end_time": "16:00", "one_off_date": "2026-11-11"})
    s = snap()
    got = occ.snapshot_occurrences(s, date(2026, 11, 1), date(2026, 12, 31), session_ids=[one["id"]])
    assert [o.date for o in got] == [date(2026, 11, 11)]
    assert occ.repeat_label(s.sessions[one["id"]]) == "разово 11.11.2026"
    assert occ.repeat_label(s.sessions[w["session"]["id"]]) == "каждую неделю"


def test_iter_occurrences_contract(admin_client):
    w = make_world(admin_client, weekday=2)
    with SessionLocal() as db:
        items = occ.iter_occurrences(db, w["session"]["id"], date(2026, 12, 28), date(2027, 1, 12))
    assert [o.date for o in items] == [date(2026, 12, 29), date(2027, 1, 5), date(2027, 1, 12)]  # через Новый год
    o = items[0]
    assert (o.start, o.end, o.status, o.source_session_id) == ("10:00", "11:00", "scheduled", w["session"]["id"])
    assert o.room_ids == (w["room"]["id"],) and o.leader_ids == (w["leader"]["id"],)


def test_t1_periods_holidays_and_parity(admin_client):
    w = make_world(admin_client, weekday=1)
    sid = w["session"]["id"]
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO academic_periods (id, name, start_date, end_date, even_week_start) VALUES (1,'Осень','2026-09-01','2026-12-27','2026-08-31')"))
        conn.execute(text("INSERT INTO no_class_days (period_id, date, reason) VALUES (1,'2026-11-02','Праздник')"))
        conn.execute(text("UPDATE sessions SET period_id = 1 WHERE id = :s"), {"s": sid})
    s = snap()
    dates = [o.date for o in occ.snapshot_occurrences(s, date(2026, 10, 26), date(2027, 1, 31), session_ids=[sid])]
    assert date(2026, 11, 2) not in dates  # неучебный день
    assert max(dates) == date(2026, 12, 21)  # после конца периода занятий нет
    assert s.calendar.parity(date(2026, 9, 2)) == "even" and s.calendar.parity(date(2026, 9, 9)) == "odd"
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET repeat = 'odd' WHERE id = :s"), {"s": sid})
    s = snap()
    odd = [o.date for o in occ.snapshot_occurrences(s, date(2026, 11, 1), date(2026, 11, 30), session_ids=[sid])]
    assert odd and all(s.calendar.parity(d) == "odd" for d in odd)
    # та же семантика, что у build_week T1
    from backend.app.routers.public import _dump_schedule_data
    with SessionLocal() as db:
        data = _dump_schedule_data(db)
    old = [e["date"] for wk in (date(2026, 11, 2) + timedelta(weeks=k) for k in range(5)) for e in build_week(wk, data) if e["session_id"] == sid]
    assert old == [d.isoformat() for d in odd]


def test_week_events_equal_build_week_in_fallback(admin_client):
    """В режиме fallback новая неделя байт-в-байт совпадает со старым build_week."""
    from backend.app.routers.public import _dump_schedule_data

    rnd = random.Random(7)
    w = make_world(admin_client, weekday=1)
    for i in range(6):
        add_extra_world(admin_client, weekday=rnd.randint(1, 6), start=f"{12 + i}:00", end=f"{12 + i}:45", name=f"C{i}")
    sid = w["session"]["id"]
    admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": sid, "original_date": "2026-11-02", "type": "cancelled", "comment": "болезнь"})
    admin_client.post("/api/admin/exceptions/moves", json={"session_id": sid, "original_date": "2026-11-09", "type": "moved", "new_date": "2026-11-18", "new_start_time": "19:00", "new_end_time": "20:00", "new_room_id": w["room"]["id"], "comment": ""})
    s = snap()
    keys = ["event_id", "session_id", "club_id", "date", "start_time", "end_time", "status", "original_date", "room_id", "leader_id", "room_name", "leader_name", "comment"]
    with SessionLocal() as db:
        data = _dump_schedule_data(db)
    for monday in (date(2026, 10, 26) + timedelta(weeks=k) for k in range(6)):
        old = [{k: e.get(k) for k in keys} for e in build_week(monday, data)]
        new = [{k: e.get(k) for k in keys} for e in occ.week_events(s, monday)]
        assert old == new, monday


# ------------------------------------------------------------------ конфликты


def test_even_and_odd_in_same_room_do_not_conflict(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=2, start="10:00", end="11:00", room_id=w["room"]["id"], name="Нечёт")
    prov = FakeProvider(autumn_calendar(), {w["session"]["id"]: "even"})
    occ.set_provider(prov)
    with SessionLocal() as db:
        found = ce.check_change(db, "update_session", other["session"]["id"], {"weekday": 1}, today=TODAY)
    assert found  # weekly vs even — пересекаются по чётным неделям
    assert all(c.a.parity == "even" for c in found)
    prov.repeats[other["session"]["id"]] = "odd"
    with SessionLocal() as db:
        assert ce.check_change(db, "update_session", other["session"]["id"], {"weekday": 1}, today=TODAY) == []


def test_conflict_reports_concrete_dates_and_both_sessions(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=2, start="10:30", end="11:30", room_id=w["room"]["id"], name="Блок")
    resp = admin_client.patch(f"/api/admin/sessions/{other['session']['id']}", json={"weekday": 1})
    assert resp.status_code == 409
    item = resp.json()["detail"]["conflicts"][0]
    assert item["session_id"] == other["session"]["id"] and item["other_session_id"] == w["session"]["id"]
    assert item["reasons"] == ["room"] and item["resource_label"] == "101"
    assert date.fromisoformat(item["date"]).isoweekday() == 1 and item["date"] >= TODAY.isoformat()
    assert item["other"]["club_name"] == "Python"


def test_holiday_frees_slot(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=3, start="10:00", end="11:00", room_id=w["room"]["id"], name="Разово")
    occ.set_provider(FakeProvider(autumn_calendar({date(2026, 11, 2): "День единства"}), {}))
    with SessionLocal() as db:
        # разовое занятие в праздник не пересекается с регулярным (его в этот день нет)
        assert ce.check_change(db, "update_session", other["session"]["id"], {"weekday": 1, "one_off_date": "2026-11-02"}, today=TODAY) == []
        assert ce.check_change(db, "update_session", other["session"]["id"], {"weekday": 1, "one_off_date": "2026-11-09"}, today=TODAY)


def test_multiple_leaders_conflict_via_session_leaders(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=1, start="10:00", end="11:00", name="Второй")
    with SessionLocal() as db:
        assert ce.check_change(db, "update_session", other["session"]["id"], {"start_time": "10:15"}, today=TODAY) == []
    with db_engine.begin() as conn:  # Иван Иванов — второй ведущий у «Второй»
        conn.execute(text("INSERT INTO session_leaders (session_id, leader_id) VALUES (:s, :a), (:s, :b)"),
                     {"s": other["session"]["id"], "a": other["leader"]["id"], "b": w["leader"]["id"]})
    s = snap()
    assert set(occ.leaders_of(s, s.sessions[other["session"]["id"]])) == {other["leader"]["id"], w["leader"]["id"]}
    found = ce.detect(s, occ.snapshot_occurrences(s, TODAY, TODAY + timedelta(days=14)))
    assert {c.resource for c in found} == {"leader"} and len(found) == 2


def test_remote_room_never_conflicts(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=1, start="10:00", end="11:00", name="Онлайн", leader_id=None)
    s = snap()
    s.sessions[other["session"]["id"]].room_id = w["room"]["id"]
    assert ce.detect(s, occ.snapshot_occurrences(s, TODAY, TODAY + timedelta(days=7)))
    s.rooms[w["room"]["id"]].is_remote = 1
    assert ce.detect(s, occ.snapshot_occurrences(s, TODAY, TODAY + timedelta(days=7))) == []


def test_cancel_then_move_into_freed_slot(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=2, start="10:00", end="11:00", room_id=w["room"]["id"], name="Сосед")
    move = {"session_id": other["session"]["id"], "original_date": "2026-11-03", "type": "moved", "new_date": "2026-11-09",
            "new_start_time": "10:00", "new_end_time": "11:00", "new_room_id": w["room"]["id"], "comment": ""}
    assert admin_client.post("/api/admin/exceptions/moves", json=move).status_code == 409
    cancel = admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": w["session"]["id"], "original_date": "2026-11-09", "type": "cancelled", "comment": ""})
    assert cancel.status_code == 201
    assert admin_client.post("/api/admin/exceptions/moves", json=move).status_code == 201
    # вернуть отменённое занятие теперь нельзя — слот занят переносом
    assert admin_client.delete(f"/api/admin/exceptions/{cancel.json()['id']}").status_code == 409


def test_override_allows_joint_session_and_report(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=2, start="10:00", end="11:00", room_id=w["room"]["id"], name="Совместно")
    assert admin_client.patch(f"/api/admin/sessions/{other['session']['id']}", json={"weekday": 1}).status_code == 409
    ov = admin_client.post("/api/admin/conflicts/overrides", json={"session_a": other["session"]["id"], "session_b": w["session"]["id"], "comment": "совместное"})
    assert ov.status_code == 201
    assert admin_client.patch(f"/api/admin/sessions/{other['session']['id']}", json={"weekday": 1}).status_code == 200
    rep = admin_client.get("/api/admin/conflicts").json()
    assert rep["items"] == []
    rep = admin_client.get("/api/admin/conflicts", params={"include_allowed": True}).json()
    assert rep["items"] and all(i["allowed"] for i in rep["items"])
    assert admin_client.delete(f"/api/admin/conflicts/overrides/{ov.json()['id']}").status_code == 204
    assert admin_client.get("/api/admin/conflicts").json()["items"]


def test_conflicts_endpoint_requires_admin(client):
    assert client.get("/api/admin/conflicts").status_code == 401


# ------------------------------------------------------------------ REST / .ics


def test_week_payload_and_occurrence_endpoints(admin_client):
    w = make_world(admin_client, weekday=1)
    occ.set_provider(FakeProvider(autumn_calendar({date(2026, 11, 2): "День единства"}), {}))
    body = admin_client.get("/api/week", params={"week": "2026-11-02"}).json()
    assert body["parity"] == "even" and body["period"]["title"] == "Осень 2026"
    assert body["no_class"] == [{"date": "2026-11-02", "title": "День единства"}]
    assert body["events"] == []
    items = admin_client.get(f"/api/sessions/{w['session']['id']}/occurrences", params={"from": "2026-10-26", "to": "2026-11-16"}).json()
    assert [i["date"] for i in items["items"]] == ["2026-10-26", "2026-11-09", "2026-11-16"]
    assert items["repeat"] == "weekly"
    club = admin_client.get(f"/api/clubs/{w['club']['id']}").json()
    assert club["sessions"][0]["next_dates"] == ["2026-11-09", "2026-11-16", "2026-11-23"]
    assert club["sessions"][0]["repeat_label"] == "каждую неделю"
    co = admin_client.get(f"/api/clubs/{w['club']['id']}/occurrences").json()
    assert co["next_dates"][0] == "2026-11-09"


def _vevents(ics: str) -> list[str]:
    return [b for b in ics.split("BEGIN:VEVENT")[1:]]


def test_ics_explicit_dates_moves_and_cancellations(admin_client):
    w = make_world(admin_client, weekday=1)
    sid = w["session"]["id"]
    admin_client.post("/api/admin/exceptions/cancellations", json={"session_id": sid, "original_date": "2026-11-02", "type": "cancelled", "comment": ""})
    admin_client.post("/api/admin/exceptions/moves", json={"session_id": sid, "original_date": "2026-11-09", "type": "moved", "new_date": "2026-11-12", "new_start_time": "18:00", "new_end_time": "19:00", "new_room_id": w["room"]["id"], "comment": ""})
    resp = admin_client.get(f"/api/clubs/{w['club']['id']}/calendar.ics", params={"from": "2026-10-26", "to": "2026-11-23"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/calendar")
    ics = resp.text
    assert "RRULE" not in ics and ics.endswith("\r\n")
    starts = [line for line in ics.split("\r\n") if line.startswith("DTSTART;")]
    assert starts == ["DTSTART;TZID=Europe/Moscow:20261026T100000", "DTSTART;TZID=Europe/Moscow:20261112T180000",
                      "DTSTART;TZID=Europe/Moscow:20261116T100000", "DTSTART;TZID=Europe/Moscow:20261123T100000"]
    uids = [line for line in ics.split("\r\n") if line.startswith("UID:")]
    assert len(set(uids)) == 4
    again = admin_client.get(f"/api/clubs/{w['club']['id']}/calendar.ics", params={"from": "2026-10-26", "to": "2026-11-23"}).text
    assert uids == [line for line in again.split("\r\n") if line.startswith("UID:")]  # стабильны
    assert "перенесено" in _vevents(ics)[1]
    full = admin_client.get("/api/calendar.ics", params={"from": "2026-10-26", "to": "2026-11-23"}).text
    assert len(_vevents(full)) == 4
    one = admin_client.get(f"/api/sessions/{sid}/calendar.ics", params={"from": "2026-10-26", "to": "2026-10-26"}).text
    assert len(_vevents(one)) == 1
    assert admin_client.get("/api/calendar.ics", params={"from": "2026-01-01", "to": "2027-12-31"}).status_code == 422


def test_ics_skips_holidays_and_wrong_parity(admin_client):
    w = make_world(admin_client, weekday=1)
    # нечётные недели ноября: 9-е и 23-е; 23-е — неучебный день
    occ.set_provider(FakeProvider(autumn_calendar({date(2026, 11, 23): "Выходной"}), {w["session"]["id"]: "odd"}))
    ics = calendar_export.build_calendar(snap(), date(2026, 11, 1), date(2026, 11, 30))
    starts = [line.split(":")[1][:8] for line in ics.split("\r\n") if line.startswith("DTSTART;")]
    assert starts == ["20261109"]


# ------------------------------------------------------------------ уведомления


def test_notifications_skip_dates_without_occurrence(admin_client, monkeypatch):
    from backend.app.services import push

    calls = []
    monkeypatch.setattr("backend.app.services.delivery.deliver", lambda db, ev: calls.append(ev) or type("R", (), {"web_sent": 1})())
    w = make_world(admin_client, weekday=1)
    sid = w["session"]["id"]
    with SessionLocal() as db:
        from backend.app.models.session_exception import SessionException

        future = SessionException(session_id=sid, original_date="2026-11-09", type="cancelled", comment="")
        past = SessionException(session_id=sid, original_date="2026-10-19", type="cancelled", comment="")
        holiday = SessionException(session_id=sid, original_date="2026-11-02", type="cancelled", comment="")
        db.add_all([future, past, holiday])
        db.commit()
        ids = future.id, past.id, holiday.id
    occ.set_provider(FakeProvider(autumn_calendar({date(2026, 11, 2): "Праздник"}), {}))
    assert push.notify_exception(ids[0]) == 1
    assert push.notify_exception(ids[1]) == 0  # прошло
    assert push.notify_exception(ids[2]) == 0  # неучебный день — занятия и так нет
    assert len(calls) == 1
    s = snap()
    assert [o.source_session_id for o in occ.reminder_targets(s, date(2026, 11, 16))] == [sid]
    assert occ.reminder_targets(s, date(2026, 11, 2)) == []


def test_broadcast_rejects_session_without_upcoming_dates(admin_client):
    w = make_world(admin_client, weekday=1)
    one = _post(admin_client, "/api/admin/sessions", {"club_id": w["club"]["id"], "room_id": w["room"]["id"], "weekday": 1,
                                                      "start_time": "15:00", "end_time": "16:00", "one_off_date": "2026-10-19"})
    s = snap()
    assert occ.sessions_without_upcoming(s, [w["session"]["id"], one["id"]]) == [one["id"]]


# ------------------------------------------------------------------ импорт


def dataset(start="10:00"):
    return {
        "version": 1,
        "rooms": [{"building": "Главный", "number": "201", "capacity": 30}, {"building": "Главный", "number": "202"}],
        "leaders": [{"full_name": "Петров  Пётр Петрович"}, {"full_name": "Сидорова Анна"}],
        "clubs": [
            {"name": "Робототехника", "category": "Техника", "leaders": ["Петров Петр Петрович"],
             "sessions": [{"weekday": 1, "start": start, "end": "11:30", "rooms": [{"building": "Главный", "number": "201"}]},
                          {"repeat": "once", "date": "2026-11-11", "start": "12:00", "end": "13:00", "rooms": [{"building": "главный", "number": "202"}]}]},
            {"name": "«Шахматы»", "category": "Игры", "leaders": ["Сидорова Анна"],
             "sessions": [{"weekday": 2, "start": "16:00", "end": "17:00", "rooms": [{"building": "Главный", "number": "202"}]}]},
        ],
    }


def _counts():
    with SessionLocal() as db:
        return {t: db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in ("clubs", "leaders", "rooms", "sessions", "categories")}


def test_import_publish_idempotent_no_duplicates(admin_client):
    r1 = admin_client.post("/api/admin/import/publish", json=dataset())
    assert r1.status_code == 200, r1.text
    assert r1.json()["stats"]["sessions_created"] == 3
    first = _counts()
    assert first == {"clubs": 2, "leaders": 2, "rooms": 2, "sessions": 3, "categories": 2}
    r2 = admin_client.post("/api/admin/import/publish", json=dataset())
    assert r2.status_code == 200
    st = r2.json()["stats"]
    assert st["sessions_created"] == 0 and st["sessions_kept"] == 3 and st["clubs_created"] == 0
    assert _counts() == first
    ds = dataset()
    ds["clubs"][1]["name"] = "шахматы"  # другой регистр/кавычки — тот же кружок
    assert admin_client.post("/api/admin/import/publish", json=ds).json()["stats"]["clubs_created"] == 0


def test_import_dry_run_and_validation(admin_client):
    r = admin_client.post("/api/admin/import/publish", params={"dry_run": True}, json=dataset())
    assert r.status_code == 200 and r.json()["dry_run"]
    assert _counts()["clubs"] == 0
    bad = dataset()
    bad["clubs"][0]["leaders"] = ["Неизвестный"]
    r = admin_client.post("/api/admin/import/publish", json=bad)
    assert r.status_code == 422 and r.json()["detail"]["errors"]


def test_import_rejected_on_conflict_and_db_untouched(admin_client):
    w = make_world(admin_client, weekday=1)
    ds = dataset()
    ds["leaders"].append({"full_name": "Иван Иванов"})
    ds["clubs"][1]["leaders"] = ["Иван Иванов"]
    ds["clubs"][1]["sessions"][0].update({"weekday": 1, "start": "10:00", "end": "11:00"})
    before = _counts()
    r = admin_client.post("/api/admin/import/publish", json=ds)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["conflicts"][0]["reasons"] == ["leader"]
    assert _counts() == before
    assert w


def test_import_backup_and_rollback(admin_client, tmp_path):
    make_world(admin_client, weekday=4)
    before = _counts()
    r = admin_client.post("/api/admin/import/publish", json=dataset())
    pub = r.json()["publish"]
    assert pub["backup"].startswith("pre-import-")
    assert (tmp_path / "backups" / pub["backup"]).exists()
    assert _counts() != before
    rb = admin_client.post(f"/api/admin/import/publishes/{pub['id']}/rollback")
    assert rb.status_code == 200, rb.text
    assert _counts() == before
    hist = admin_client.get("/api/admin/import/publishes").json()["items"]
    assert hist[0]["rollback_of"] == pub["id"]


def test_import_prune_removes_dropped_sessions(admin_client):
    admin_client.post("/api/admin/import/publish", json=dataset())
    ds = dataset(start="09:00")
    r = admin_client.post("/api/admin/import/publish", json=ds).json()["stats"]
    assert r["sessions_created"] == 1 and r["sessions_deleted"] == 1
    assert _counts()["sessions"] == 3


def test_norm():
    assert import_publish.norm(" Петров  Пётр ") == import_publish.norm("петров петр")
    assert import_publish.norm("«Шахматы»") == "шахматы"


# ------------------------------------------------------------------ бэкап / восстановление


def test_backup_prefix_rotation_and_verified_restore(admin_client, tmp_path):
    from backend.app import cli

    make_world(admin_client, weekday=1)
    nightly = cli.backup(tmp_path, keep=1, prefix="clubs")
    pre = cli.backup(tmp_path, keep=1, prefix="pre-migrate")
    cli.backup(tmp_path, keep=1, prefix="clubs")
    assert pre.exists() and not nightly.exists()  # ротация не задевает чужой префикс
    assert cli.verify_backup(pre)["integrity"] == "ok"
    before = _counts()
    admin_client.post("/api/admin/import/publish", json=dataset())
    assert _counts() != before
    assert cli.restore(pre)["integrity"] == "ok"
    assert _counts() == before
    with pytest.raises(cli.CliError):
        cli.restore(tmp_path / "missing.sqlite3.gz")


def test_t3_draft_publish_is_journaled_and_rolls_back(admin_client):
    from .test_import_drafts import docx

    world = make_world(admin_client)
    rows = [["День", "Кружок", "Руководитель", "Время", "Аудитория"], ["Среда", "Из черновика", "Кто-то", "13:00 – 14:00", "101"]]
    draft = _post(admin_client, "/api/admin/imports", {"filename": "s.docx", "content_base64": docx(rows)})
    choice = {"row": 2, "action": "create", "category_id": world["category"]["id"], "leader_id": world["leader"]["id"], "room_ids": [world["room"]["id"]]}
    admin_client.put(f"/api/admin/imports/{draft['id']}/decisions", json={"decisions": [choice]})
    published = admin_client.post(f"/api/admin/imports/{draft['id']}/publish").json()
    entry = next(i for i in import_publish.history() if i["id"] == published["publish_id"])
    assert entry["draft_id"] == draft["id"] and entry["backup"] and entry["stats"]["sessions_created"] == 1
    assert any(c["name"] == "Из черновика" for c in admin_client.get("/api/admin/clubs").json())
    import_publish.rollback(published["publish_id"])
    db_engine.dispose()
    assert all(c["name"] != "Из черновика" for c in admin_client.get("/api/admin/clubs").json())


def test_update_session_extra_rooms_are_checked(admin_client):
    w = make_world(admin_client, weekday=1)
    other = add_extra_world(admin_client, weekday=1, start="10:00", end="11:00", name="Соседи")
    with SessionLocal() as db:
        assert ce.check_change(db, "update_session", other["session"]["id"], {"room_ids": [other["room"]["id"]]}, today=TODAY) == []
        found = ce.check_change(db, "update_session", other["session"]["id"], {"room_ids": [other["room"]["id"], w["room"]["id"]]}, today=TODAY)
    assert found and {c.resource for c in found} == {"room"}
