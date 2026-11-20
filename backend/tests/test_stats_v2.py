"""Статистика v2: уровень А с версией и каналом, уровень Б (HMAC, маска дней), удержание, свёртка 90 дней,
вкладка «Статистика» и CSV, маска IP в журнале приложения."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from backend.app.database import SessionLocal
from backend.app.models import AppDevice, Broadcast, BroadcastReceipt, Club
from backend.app.models.usage import (
    ClientErrorCount,
    InstallActivity,
    PerfDaily,
    RetentionWeekly,
    UsageBatch,
    UsageDaily,
    UsageMonthly,
    VersionDaily,
)
from backend.app.privacy import mask_ip
from backend.app.services import client_logs, stats_report, usage

from .test_exception_conflicts_api import admin_client  # noqa: F401

TODAY = date(2026, 11, 20)


def batch(n: str, **kw):
    return {"batch_id": n * 32, "platform": "android", "channel": "i", "version": "1.9.024", **kw}


@pytest.fixture(autouse=True)
def _limits():
    usage.reset_limits()
    client_logs.reset_limits()
    yield


# ---------- уровень А ----------

def test_batch_with_version_channel_dims_and_perf(admin_client):
    body = batch("a", events=[{"metric": "screen_view", "dim": "week"}, {"metric": "club_view", "dim": "c42"},
                              {"metric": "fb_rating", "dim": "5"}, {"metric": "api_error", "dim": "schedule_5xx"},
                              {"metric": "update_done", "dim": "1.9.024"}],
                 perf=[{"metric": "lcp", "bucket": "b2"}, {"metric": "ttfs", "bucket": "b1"}],
                 errors=[{"code": "TypeError", "source": "app.js", "line": 3}])
    r = admin_client.post("/api/app/usage", json=body)
    assert r.status_code == 202 and r.json()["accepted"] == 8
    with SessionLocal() as db:
        rows = db.scalars(select(UsageDaily)).all()
        assert {(x.platform, x.channel, x.version) for x in rows} == {("android", "i", "1.9.024")}
        assert {x.dim for x in rows} == {"week", "c42", "5", "schedule_5xx", "1.9.024"}
        assert db.scalar(select(func.count()).select_from(PerfDaily)) == 2
        assert db.scalar(select(ClientErrorCount.build)) == "1.9.024"


@pytest.mark.parametrize("dim", ["free text", "c", "c1234567", "1.9.24", "schedule_6xx", "x" * 33, "user@mail.ru"])
def test_dim_outside_closed_list_rejected(admin_client, dim):
    assert admin_client.post("/api/app/usage", json=batch("b", events=[{"metric": "screen_view", "dim": dim}])).status_code == 422


def test_old_clients_bucket_field_still_accepted(admin_client):
    body = {"batch_id": "c" * 32, "platform": "web", "events": [{"metric": "search_results", "bucket": "few"}]}
    assert admin_client.post("/api/app/usage", json=body).status_code == 202
    with SessionLocal() as db:
        row = db.scalars(select(UsageDaily)).one()
        assert (row.dim, row.channel, row.version) == ("few", "p", "")


def test_usage_rate_limit_is_per_ip_in_memory():
    for _ in range(usage.RATE):
        assert usage.allow("usage-ip:1", now=0)
    assert not usage.allow("usage-ip:1", now=1)
    assert usage.allow("usage-ip:1", now=usage.WINDOW + 2)


def test_server_counts_apk_download_once_without_identifiers(client, tmp_path, monkeypatch):
    client.get("/android/download", follow_redirects=False)
    client.get("/android/download", headers={"Range": "bytes=100-"}, follow_redirects=False)
    with SessionLocal() as db:
        row = db.scalars(select(UsageDaily).where(UsageDaily.metric == "apk_download")).one()
        assert (row.platform, row.dim, row.count) == ("server", "server", 1)


# ---------- уровень Б ----------

def test_activity_stores_hmac_bits_and_version_adoption(client):
    install = "z" * 32
    with SessionLocal() as db:
        for offset, ver in ((0, "1.9.023"), (1, "1.9.023"), (3, "1.9.024")):
            usage.activity(db, usage.ActivityIn(install_id=install, kind="android", channel="i", version="v" + ver + "ibA"),
                           day=TODAY + timedelta(days=offset))
        row = db.scalars(select(InstallActivity)).one()
        assert install not in row.id_hmac and row.id_hmac == usage.activity_key(install) and len(row.id_hmac) == 64
        assert (row.platform, row.channel, row.version, row.first_day) == ("android", "i", "1.9.024", TODAY)
        assert int(row.days_bits, 16) == 0b1101  # дни 3, 1, 0 → биты 0, 2, 3 (бит 0 = last_day)
        assert [usage.active_on(row, TODAY + timedelta(days=d)) for d in range(4)] == [True, True, False, True]
        adoption = {(v.day, v.version): v.active for v in db.scalars(select(VersionDaily))}
        assert adoption == {(TODAY, "1.9.023"): 1, (TODAY + timedelta(days=1), "1.9.023"): 1, (TODAY + timedelta(days=3), "1.9.024"): 1}
        assert {c.name for c in InstallActivity.__table__.columns} == {
            "id_hmac", "platform", "channel", "version", "first_day", "last_day", "days_bits"}


def test_bits_are_bounded_to_120_days():
    bits = usage.shift_bits(1, TODAY, TODAY + timedelta(days=500))
    assert bits == 1 and bits.bit_length() <= usage.ACTIVITY_DAYS
    full = usage.shift_bits((1 << 120) - 1, TODAY, TODAY + timedelta(days=1))
    assert full.bit_length() == 120
    assert usage.shift_bits(0b1, TODAY, TODAY - timedelta(days=2)) == 0b101  # поздний пинг за прошлый день


def test_ping_endpoint_feeds_level_b_and_skips_installs_for_apk(client):
    assert client.post("/api/app/ping", json={"install_id": "q" * 32, "kind": "android", "channel": "i", "version": "1.9.024"}).status_code == 204
    assert client.post("/api/app/ping", json={"install_id": "w" * 32, "kind": "web"}).status_code == 204
    assert client.post("/api/app/ping", json={"install_id": "w" * 32, "kind": "web", "extra": "x"}).status_code == 422
    with SessionLocal() as db:
        assert {r.platform for r in db.scalars(select(InstallActivity))} == {"android", "web"}
        from backend.app.models import Install
        assert db.scalar(select(func.count()).select_from(Install)) == 1


def _install(db, key, first, days, platform="web"):
    last = max(days)
    bits = 0
    for d in days:
        bits |= 1 << (last - d)
    db.add(InstallActivity(id_hmac=key, platform=platform, channel="p", version="1.9.024", first_day=first,
                           last_day=first + timedelta(days=last), days_bits=format(bits, "x")))


def test_retention_cohorts_and_d1_d7_d30():
    monday = TODAY - timedelta(days=TODAY.weekday() + 28)  # 4 недели назад
    with SessionLocal() as db:
        _install(db, "a" * 64, monday, [0, 1, 7, 8])       # D1, D7, недели 0 и 1
        _install(db, "b" * 64, monday + timedelta(days=2), [0, 30])  # D30, неделя 4
        _install(db, "c" * 64, monday, [0])                 # ушёл в первый день
        db.commit()
        usage.compute_retention(db, today=TODAY)
        rows = {r.week_n: (r.size, r.active) for r in db.scalars(select(RetentionWeekly).where(RetentionWeekly.cohort_week == monday))}
        assert rows[0] == (3, 3) and rows[1] == (3, 1) and rows[2] == (3, 0) and rows[4] == (3, 1)
        days = usage.day_retention(db.scalars(select(InstallActivity)).all(), TODAY)
        assert days["d1"] == {"cohort": 3, "kept": 1, "rate": 0.333}
        assert days["d7"]["kept"] == 1 and days["d30"]["kept"] == 1
        usage.compute_retention(db, today=TODAY)  # идемпотентно
        assert db.scalar(select(func.count()).select_from(RetentionWeekly)) == len(rows)


def test_rollup_after_90_days_to_monthly_and_retention_limits():
    old, fresh = TODAY - timedelta(days=90), TODAY - timedelta(days=89)
    with SessionLocal() as db:
        for d, n in ((old, 3), (old - timedelta(days=1), 2), (fresh, 7)):
            db.add(UsageDaily(day=d, platform="ios", channel="p", version="1.9.023", metric="screen_view", dim="week", count=n))
        db.add(PerfDaily(day=old, platform="web", version="1.9.023", metric="lcp", bucket="b2", count=4))
        db.add(ClientErrorCount(day=old, platform="web", build="1.9.023", code="TypeError", source="a.js", line=1, count=6))
        db.add(UsageBatch(id="1" * 32, day=TODAY - timedelta(days=3)))
        db.add(UsageMonthly(month="2024-10", platform="web", channel="p", version="1.8", metric="page_open", dim="home", count=1))
        db.add(VersionDaily(day=TODAY - timedelta(days=800), platform="web", version="1.0.001", active=1))
        _install(db, "gone" * 16, TODAY - timedelta(days=200), [0, 70])  # последний день 130 дней назад
        _install(db, "kept" * 16, TODAY - timedelta(days=10), [0])
        db.commit()
        result = usage.rollup(db, today=TODAY)
        assert result == {"rolled_up": 4, "forgotten_installs": 1}
        assert [r.day for r in db.scalars(select(UsageDaily))] == [fresh]
        monthly = {(m.month, m.version, m.metric, m.dim): m.count for m in db.scalars(select(UsageMonthly))}
        assert monthly[(old.strftime("%Y-%m"), "1.9", "screen_view", "week")] == 5 or (
            monthly[(old.strftime("%Y-%m"), "1.9", "screen_view", "week")] + monthly.get(((old - timedelta(days=1)).strftime("%Y-%m"), "1.9", "screen_view", "week"), 0) == 5)
        assert monthly[(old.strftime("%Y-%m"), "1.9", "perf_lcp", "b2")] == 4
        assert monthly[(old.strftime("%Y-%m"), "1.9", "js_error", "TypeError")] == 6
        assert ("2024-10", "1.8", "page_open", "home") not in monthly  # старше 2 лет
        assert db.scalar(select(func.count()).select_from(PerfDaily)) == 0
        assert db.scalar(select(func.count()).select_from(ClientErrorCount)) == 0
        assert db.scalar(select(func.count()).select_from(UsageBatch)) == 0
        assert db.scalar(select(func.count()).select_from(VersionDaily)) == 0
        assert [r.id_hmac[:4] for r in db.scalars(select(InstallActivity))] == ["kept"]
        assert usage.rollup(db, today=TODAY)["rolled_up"] == 0  # повтор ничего не удваивает
        assert sum(m.count for m in db.scalars(select(UsageMonthly).where(UsageMonthly.metric == "screen_view"))) == 5


def test_minor_version():
    assert usage.minor("1.9.024") == "1.9" and usage.minor("") == "" and usage.minor("local") == ""


# ---------- вкладка «Статистика» ----------

def _seed_report(db):
    today = usage.today_msk()
    from backend.app.models import Category, Leader
    db.add(Category(id=70, name="Техника", color="#112233"))
    db.add(Leader(id=70, name="Руководитель", position="", contact=""))
    db.flush()
    db.add(Club(id=7, name="Робототехника", description="", category_id=70, leader_id=70, is_active=True))
    for metric, dim, n in (("screen_view", "week", 10), ("club_view", "c7", 4), ("fb_rating", "5", 3), ("fb_rating", "2", 1),
                           ("fb_prompt_shown", "prompt_usage", 6), ("api_error", "schedule_5xx", 2), ("native_crash", "webview", 1),
                           ("install_banner", "none", 9), ("installed", "none", 2), ("apk_page", "none", 5), ("apk_download", "none", 3),
                           ("push_shown", "web", 4), ("push_open", "web", 1)):
        db.add(UsageDaily(day=today, platform="android", channel="i", version="1.9.024", metric=metric, dim=dim, count=n))
    db.add(UsageDaily(day=today, platform="server", channel="p", version="", metric="apk_download", dim="server", count=2))
    for b, n in (("b1", 6), ("b2", 3), ("b4", 1)):
        db.add(PerfDaily(day=today, platform="web", version="1.9.024", metric="lcp", bucket=b, count=n))
    db.add(ClientErrorCount(day=today, platform="web", build="1.9.024", code="TypeError", source="new.js", line=5, count=2))
    db.add(ClientErrorCount(day=today, platform="web", build="1.9.023", code="Error", source="old.js", line=1, count=1))
    db.add(ClientErrorCount(day=today, platform="web", build="1.9.024", code="Error", source="old.js", line=1, count=1))
    db.add(VersionDaily(day=today, platform="android", version="1.9.024", active=3))
    db.add(VersionDaily(day=today, platform="android", version="1.9.023", active=1))
    _install(db, "r" * 64, today - timedelta(days=2), [0, 1, 2], platform="android")
    bc = Broadcast(title="Тест", body="", audience="all", web_sent=5, web_failed=1, fcm_sent=3, fcm_failed=0)
    db.add(bc)
    db.flush()
    db.add(BroadcastReceipt(broadcast_id=bc.id, install_hash="h" * 64, channel="android", shown_at=usage.today_msk(), opened_at=None))
    db.commit()


def test_report_blocks_and_csv(admin_client):
    with SessionLocal() as db:
        _seed_report(db)
    r = admin_client.get("/api/admin/stats/report?days=30")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert set(stats_report.BLOCKS) <= set(data)
    assert data["users"]["today"]["dau"] == 1 and data["users"]["today"]["by_platform"]["android"] == 1
    assert data["versions"]["latest"] == "1.9.024" and data["versions"]["on_old"] == 1
    apk = {s["metric"]: s["count"] for s in data["funnels"]["apk"]}
    assert apk == {"apk_page": 5, "apk_download": 3, "apk_download_server": 2, "apk_first_run": 0}
    assert data["usage"]["top_clubs"][0] == {"club_id": 7, "name": "Робототехника", "count": 4}
    assert data["push"]["channels"]["fcm"]["sent"] == 3 and data["push"]["channels"]["fcm"]["shown"] == 1
    assert data["push"]["channels"]["web"]["failed"] == 1 and data["push"]["client"]["push_open"] == {"web": 1}
    q = data["quality"]
    assert q["latest"] == "1.9.024" and [e["source"] for e in q["new_after_release"]] == ["new.js"]
    assert q["perf"][0]["p50"] == "b1" and q["perf"][0]["p75"] == "b2"
    assert q["api_errors"] == [{"dim": "schedule_5xx", "count": 2}] and q["native_crashes"] == [{"dim": "webview", "count": 1}]
    fb = data["feedback"]
    assert fb["overall"]["avg"] == 4.25 and fb["by_version"]["1.9.024"]["count"] == 4
    assert fb["prompts"]["fb_prompt_shown"] == {"prompt_usage": 6}
    for block in stats_report.BLOCKS:
        c = admin_client.get(f"/api/admin/stats/export.csv?block={block}&days=30")
        assert c.status_code == 200 and c.headers["content-type"].startswith("text/csv")
        assert f"kipclub-stats-{block}-" in c.headers["content-disposition"] and c.text.startswith("\ufeff")
    assert "Робототехника" in admin_client.get("/api/admin/stats/export.csv?block=usage").text
    assert admin_client.get("/api/admin/stats/export.csv?block=../etc").status_code == 422


def test_report_empty_db_and_requires_admin(admin_client, client):
    data = admin_client.get("/api/admin/stats/report").json()
    assert data["days"] == 90 and data["users"]["stickiness"] is None and data["feedback"]["overall"]["avg"] is None
    for block in stats_report.BLOCKS:
        assert admin_client.get(f"/api/admin/stats/export.csv?block={block}").status_code == 200
    admin_client.post("/api/admin/logout")
    from fastapi.testclient import TestClient

    from backend.app.main import app
    anon = TestClient(app)
    assert anon.get("/api/admin/stats/report").status_code == 401
    assert anon.get("/api/admin/stats/export.csv?block=users").status_code == 401


def test_csv_rows_unknown_block():
    with pytest.raises(KeyError):
        stats_report.csv_rows("nope", {})


def test_apk_device_has_first_seen(client):
    from backend.app.services import broadcast as broadcast_service
    with SessionLocal() as db:
        broadcast_service.register_device(db, "d" * 32, None, "android", "1.9.024", [], True, True)
        row = db.scalars(select(AppDevice)).one()
        assert row.first_seen is not None and row.first_seen <= row.last_seen


# ---------- маска IP ----------

@pytest.mark.parametrize("raw, masked", [
    ("203.0.113.57", "203.0.113.0/24"),
    ("2001:db8:1:2:3::5", "2001:db8:1::/48"),
    ("::ffff:198.51.100.9", "198.51.100.0/24"),
    ("[2001:db8::1]", "2001:db8::/48"),
    ("fe80::1%eth0", "fe80::/48"),
    ("testclient", "-"), ("", "-"), (None, "-"),
])
def test_mask_ip(raw, masked):
    assert mask_ip(raw) == masked


def test_access_log_has_masked_ip_and_no_user_agent(client, caplog, monkeypatch):
    from starlette.requests import Request
    monkeypatch.setattr(Request, "client", property(lambda self: type("C", (), {"host": "198.51.100.77", "port": 1})()))
    with caplog.at_level(logging.INFO, logger="clubs.access"):
        client.get("/api/app/info", headers={"User-Agent": "Mozilla/5.0 SecretPhone"})
    line = next(r.getMessage() for r in caplog.records if r.name == "clubs.access" and "/api/app/info" in r.getMessage())
    assert "ip=198.51.100.0/24" in line and "198.51.100.77" not in line and "SecretPhone" not in line
