"""Автопуш о новой версии APK: первый запуск только запоминает, новая версия — ровно одна рассылка, переживает перезапуск."""
from __future__ import annotations

import json

import pytest

from backend.app.database import SessionLocal
from backend.app.models import AppDevice
from backend.app.services import delivery, fcm
from backend.app.services import release_notify as rn


@pytest.fixture
def env(tmp_path, monkeypatch):
    rel = tmp_path / "rel"
    rel.mkdir()
    monkeypatch.setenv("APP_RELEASES_DIR", str(rel))
    monkeypatch.setenv("RELEASE_NOTIFY_STATE", str(tmp_path / "state.json"))
    sent = []
    monkeypatch.setattr(fcm, "enabled", lambda: True)
    monkeypatch.setattr(fcm, "send_one", lambda token, data, collapse=None: sent.append((token, data, collapse)))
    with SessionLocal() as db:
        db.add_all([AppDevice(id_hash="a", club_ids="[]", fcm_token="t1", announcements=False, notify_changes=False),
                    AppDevice(id_hash="b", club_ids="[1]", fcm_token="t2"),
                    AppDevice(id_hash="c", club_ids="[]", fcm_token=None)])
        db.commit()

    def publish(code, version):
        (rel / f"kipclub-{code}.apk").write_bytes(b"apk")
        (rel / "latest.json").write_text(json.dumps({"file": f"kipclub-{code}.apk", "version": version, "versionCode": code}))
    return publish, sent, tmp_path / "state.json"


def run():
    with SessionLocal() as db:
        return rn.check(db)


def test_no_release_no_state(env):
    _, sent, state = env
    assert run() is None and not state.exists() and sent == []


def test_first_run_initialises_without_push_then_new_version_pushes_once(env):
    publish, sent, state = env
    publish(15, "0.7.016")
    assert run() is None and sent == [] and json.loads(state.read_text())["versionCode"] == 15
    assert run() is None and sent == []
    publish(16, "0.8.467")
    r = run()
    assert r == {"versionCode": 16, "fcm_sent": 2, "fcm_failed": 0}
    assert {t for t, _, _ in sent} == {"t1", "t2"}  # все активные с токеном, независимо от «моих кружков» и объявлений
    data = sent[0][1]
    assert data["type"] == "update-available" and data["title"] == "KipClub" and data["body"] == "Доступно обновление v0.8.467"
    assert data["url"] == "/?update=1" and data["version"] == "0.8.467" and sent[0][2] == "update-16"
    # повтор и «перезапуск» (состояние в файле) — без повторной рассылки
    assert run() is None and run() is None and len(sent) == 2
    assert json.loads(state.read_text())["versionCode"] == 16


def test_failed_send_is_not_retried(env, monkeypatch):
    publish, sent, state = env
    publish(15, "0.7.016")
    run()
    monkeypatch.setattr(fcm, "send_one", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    publish(16, "v0.8.467")
    assert run()["fcm_failed"] == 2
    assert run() is None


def test_web_subscribers_not_notified(env, monkeypatch):
    publish, sent, _ = env
    called = []
    monkeypatch.setattr(delivery, "_send_web", lambda *a: called.append(1))
    publish(15, "1")
    run()
    publish(16, "2")
    run()
    assert called == []
