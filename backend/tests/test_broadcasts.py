"""Рассылки администратора: доступ, аудитория, охват, доставка Web Push, защита от двойной отправки, лента для APK."""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import AppDevice, Broadcast, PushSubscription
from backend.app.services import broadcast as service
from backend.app.services import push as push_service

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401
from .test_push import make_keys

EP = "https://fcm.googleapis.com/fcm/send/"


def subscribe(client, name, club_id=None):
    body = {"endpoint": EP + name, "keys": make_keys()[1]}
    if club_id is not None:
        body["club_id"] = club_id
    assert client.post("/api/push/subscribe", json=body).status_code in (200, 201)


def second_club(client, w):
    return _post(client, "/api/admin/clubs", {"name": "Шахматы", "description": "", "category_id": w["club"]["category_id"],
                                              "leader_id": w["club"]["leader_id"]})


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push_service, "send_one", lambda info, data: calls.append((info["endpoint"], data)))
    return calls


def msg(key="key-00000001", **kw):
    return {"title": "Собрание", "body": "В пятницу в 15:00, актовый зал", "idempotency_key": key, **kw}


def test_admin_only(client):
    assert client.get("/api/admin/broadcasts").status_code == 401
    assert client.post("/api/admin/broadcasts/estimate", json={}).status_code == 401
    assert client.post("/api/admin/broadcasts", json=msg()).status_code == 401


def test_cross_origin_cookie_send_is_blocked(admin_client, sent):
    r = admin_client.post("/api/admin/broadcasts", json=msg(), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not sent


def test_estimate_and_send_filtered_by_clubs(admin_client, sent, caplog):
    w = make_world(admin_client)
    other = second_club(admin_client, w)
    subscribe(admin_client, "a", w["club"]["id"])
    subscribe(admin_client, "a", other["id"])      # тот же браузер на два кружка — одно уведомление
    subscribe(admin_client, "b", other["id"])
    subscribe(admin_client, "all")                  # «все кружки» получает и адресные
    with SessionLocal() as db:
        service.touch_device(db, "d" * 20, [w["club"]["id"]])
        service.touch_device(db, "e" * 20, [other["id"]])
        service.touch_device(db, "f" * 20, [w["club"]["id"]], announcements=False)
    est = admin_client.post("/api/admin/broadcasts/estimate", json={"audience": "clubs", "club_ids": [w["club"]["id"]]}).json()
    assert est == {"web": 2, "apk": 1, "fcm": 0}
    assert admin_client.post("/api/admin/broadcasts/estimate", json={"audience": "all"}).json() == {"web": 3, "apk": 2, "fcm": 0}

    caplog.set_level(logging.INFO, logger="clubs.audit")
    r = admin_client.post("/api/admin/broadcasts", json=msg(audience="clubs", club_ids=[w["club"]["id"]],
                                                            session_ids=[w["session"]["id"]], url=f"/club.html?id={w['club']['id']}"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert (j["web_sent"], j["web_failed"], j["apk_targets"], j["duplicate"]) == (2, 0, 1, False)
    assert j["author"] == "admin" and j["club_names"] == ["Python"] and j["created_at"].endswith("Z")
    assert sorted(e for e, _ in sent) == [EP + "a", EP + "all"]
    assert sent[0][1]["kind"] == "announcement" and sent[0][1]["url"] == f"/club.html?id={w['club']['id']}"
    assert any('"broadcast_sent"' in m for m in caplog.messages)

    hist = admin_client.get("/api/admin/broadcasts").json()["items"]
    assert [h["id"] for h in hist] == [j["id"]]


def test_announcements_opt_out_for_web(admin_client, sent):
    subscribe(admin_client, "x")
    assert admin_client.post("/api/push/preferences", json={"endpoint": EP + "x", "announcements": False}).json()["updated"] == 1
    assert admin_client.post("/api/push/status", json={"endpoint": EP + "x"}).json()["announcements"] is False
    assert admin_client.post("/api/admin/broadcasts", json=msg()).json()["web_sent"] == 0 and not sent


def test_dead_and_failing_subscriptions(admin_client, monkeypatch):
    subscribe(admin_client, "gone")
    subscribe(admin_client, "boom")

    def fake(info, data):
        if info["endpoint"].endswith("gone"):
            raise push_service.PushGone("410")
        raise RuntimeError("network")
    monkeypatch.setattr(push_service, "send_one", fake)
    j = admin_client.post("/api/admin/broadcasts", json=msg()).json()
    assert (j["web_sent"], j["web_failed"]) == (0, 2)
    with SessionLocal() as db:
        assert [s.endpoint for s in db.scalars(select(PushSubscription))] == [EP + "boom"]


def test_idempotency_and_content_dedupe(admin_client, sent):
    subscribe(admin_client, "a")
    first = admin_client.post("/api/admin/broadcasts", json=msg("same-key-1"))
    again = admin_client.post("/api/admin/broadcasts", json=msg("same-key-1"))
    assert first.status_code == 201 and again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["id"] == first.json()["id"] and len(sent) == 1
    dup = admin_client.post("/api/admin/broadcasts", json=msg("other-key-2"))
    assert dup.status_code == 409 and len(sent) == 1
    with SessionLocal() as db:  # через пару минут то же самое можно отправить снова
        db.get(Broadcast, first.json()["id"]).created_at -= timedelta(minutes=5)
        db.commit()
    assert admin_client.post("/api/admin/broadcasts", json=msg("other-key-2")).status_code == 201


@pytest.mark.parametrize("bad", [
    {"title": ""}, {"title": "x" * 81}, {"body": " "}, {"body": "x" * 501}, {"idempotency_key": "short"},
    {"url": "https://evil.example"}, {"url": "//evil.example"}, {"audience": "clubs"}, {"audience": "teachers"},
    {"extra": 1},
])
def test_validation(admin_client, sent, bad):
    assert admin_client.post("/api/admin/broadcasts", json={**msg(), **bad}).status_code == 422 and not sent


def test_unknown_club_and_foreign_session(admin_client, sent):
    w = make_world(admin_client)
    other = second_club(admin_client, w)
    assert admin_client.post("/api/admin/broadcasts", json=msg(audience="clubs", club_ids=[999])).status_code == 422
    r = admin_client.post("/api/admin/broadcasts", json=msg(audience="clubs", club_ids=[other["id"]], session_ids=[w["session"]["id"]]))
    assert r.status_code == 422 and not sent
    assert admin_client.post("/api/admin/broadcasts/estimate", json={"audience": "clubs", "club_ids": [999]}).status_code == 422


def test_public_feed_filters_by_clubs_and_since(admin_client, sent):
    w = make_world(admin_client)
    other = second_club(admin_client, w)
    a = admin_client.post("/api/admin/broadcasts", json=msg("k-all-0001", title="Всем")).json()
    b = admin_client.post("/api/admin/broadcasts", json=msg("k-club-001", title="Python", audience="clubs", club_ids=[w["club"]["id"]])).json()
    c = admin_client.post("/api/admin/broadcasts", json=msg("k-oth-0001", title="Шахматы", audience="clubs", club_ids=[other["id"]])).json()
    admin_client.cookies.clear()  # лента публичная
    feed = admin_client.get(f"/api/announcements?clubs={w['club']['id']}").json()
    assert [i["id"] for i in feed["items"]] == [a["id"], b["id"]] and feed["last_id"] == c["id"]
    assert [i["id"] for i in admin_client.get("/api/announcements").json()["items"]] == [a["id"]]
    assert admin_client.get(f"/api/announcements?since={b['id']}&clubs={w['club']['id']},{other['id']}").json()["items"][0]["id"] == c["id"]
    off = admin_client.get(f"/api/announcements?off=1&device={'z' * 20}&clubs={other['id']}").json()
    assert off["items"] == [] and off["last_id"] == c["id"]
    with SessionLocal() as db:
        dev = db.scalar(select(AppDevice))
        assert dev.announcements is False and json.loads(dev.club_ids) == [other["id"]] and "z" not in dev.id_hash
    assert admin_client.get("/api/announcements?clubs=abc").status_code == 422
    assert admin_client.get("/api/announcements?device=bad!id").status_code == 422


def test_feed_skips_old_and_device_touch_updates(admin_client, sent):
    old = admin_client.post("/api/admin/broadcasts", json=msg("k-old-0001")).json()
    with SessionLocal() as db:
        db.get(Broadcast, old["id"]).created_at -= timedelta(days=30)
        service.touch_device(db, "q" * 20, [1])
        service.touch_device(db, "q" * 20, [2, 2])
        assert json.loads(db.scalar(select(AppDevice)).club_ids) == [2]
        db.commit()
    assert admin_client.get("/api/announcements").json()["items"] == []
    assert service.ids("not json") == []


def test_new_subscription_inherits_announcements_opt_out(admin_client):
    w = make_world(admin_client)
    other = second_club(admin_client, w)
    subscribe(admin_client, "inh", w["club"]["id"])
    assert admin_client.post("/api/push/preferences", json={"endpoint": EP + "inh", "announcements": False}).json()["updated"] == 1
    subscribe(admin_client, "inh", other["id"])
    with SessionLocal() as db:
        rows = db.scalars(select(PushSubscription.announcements).where(PushSubscription.endpoint == EP + "inh")).all()
    assert rows == [False, False]
    assert admin_client.post("/api/push/status", json={"endpoint": EP + "inh"}).json()["announcements"] is False
