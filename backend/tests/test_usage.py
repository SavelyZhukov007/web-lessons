from datetime import timedelta

from sqlalchemy import func, select

from backend.app.database import SessionLocal
from backend.app.models.usage import ClientErrorCount, UsageBatch, UsageCounter
from backend.app.services import usage

from .test_exception_conflicts_api import admin_client  # noqa: F401

BODY = {
    "batch_id": "a" * 32,
    "platform": "web",
    "build": "local",
    "events": [{"metric": "search_results", "bucket": "none"}, {"metric": "search_abandon"}],
    "errors": [{"code": "TypeError", "source": "schedule.js", "line": 123}],
}


def test_public_batch_aggregate_dedup_and_no_user_identifier(admin_client):
    first = admin_client.post("/api/app/usage", json=BODY)
    assert first.status_code == 202 and first.json() == {"accepted": 3, "duplicate": False}
    assert admin_client.post("/api/app/usage", json=BODY).json()["duplicate"]
    report = admin_client.get("/api/admin/stats").json()["usage"]
    assert report["retention_days"] == 30 and len(report["events"]) == 2
    assert report["errors"][0]["source"] == "schedule.js" and report["errors"][0]["count"] == 1
    assert set(report["errors"][0]) == {"platform", "build", "code", "source", "line", "count"}
    another = {**BODY, "batch_id": "b" * 32}
    assert admin_client.post("/api/app/usage", json=another).status_code == 202
    assert admin_client.get("/api/admin/stats").json()["usage"]["errors"][0]["count"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UsageBatch)) == 2


def test_rejects_raw_queries_identifiers_messages_and_unbounded_data(admin_client):
    for body in [
        dict(BODY, query="private"),
        dict(BODY, install_id="tracking"),
        dict(BODY, events=[{"metric": "search_results", "query": "private"}]),
        dict(BODY, errors=[{"code": "TypeError", "message": "private"}]),
        dict(BODY, errors=[{"code": "TypeError", "source": "https://private/?token=secret"}]),
        dict(BODY, events=[{"metric": "arbitrary"}]),
        dict(BODY, events=[{"metric": "search_open"}] * 21),
        dict(BODY, batch_id="../not-a-batch"),
    ]:
        assert admin_client.post("/api/app/usage", json=body).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UsageBatch)) == 0


def test_retention_cleanup_without_new_events(admin_client):
    day = usage.today_msk() - timedelta(days=30)
    with SessionLocal() as db:
        db.add(UsageBatch(id="f" * 32, day=day))
        db.add(UsageCounter(day=day, platform="web", metric="page_open", bucket="home", count=5))
        db.add(ClientErrorCount(day=day, platform="web", build="local", code="Error", source="x.js", line=1, count=2))
        db.commit()
        usage.cleanup(db)
        for model in (UsageBatch, UsageCounter, ClientErrorCount):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_empty_batch_does_not_store_and_same_batch_counts_multiple_events(admin_client):
    assert admin_client.post("/api/app/usage", json={"batch_id": "c" * 32, "platform": "ios"}).json()["accepted"] == 0
    body = {**BODY, "events": [{"metric": "search_open"}] * 3, "errors": []}
    assert admin_client.post("/api/app/usage", json=body).status_code == 202
    assert admin_client.get("/api/admin/stats").json()["usage"]["events"] == [{"metric": "search_open", "bucket": "none", "count": 3}]
