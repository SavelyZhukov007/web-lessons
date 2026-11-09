from __future__ import annotations

from .test_exception_conflicts_api import _post, admin_client, make_world  # noqa: F401
from .test_import_drafts import docx


def ledger(client):
    result = client.get("/api/admin/actions")
    assert result.status_code == 200, result.text
    return result.json()["items"]


def test_action_undo_and_request_correlation(admin_client):
    response = admin_client.post("/api/admin/rooms", json={"name": "300", "building": "Г"}, headers={"X-Request-ID": "undo-room-001"})
    assert response.status_code == 201, response.text
    action = admin_client.get("/api/admin/actions?request_id=undo-room-001").json()["items"][0]
    assert action["kind"] == "action" and action["rollback_available"]
    assert admin_client.get("/api/admin/import/publishes").json()["items"] == []
    undone = admin_client.post(f"/api/admin/actions/{action['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert admin_client.get("/api/admin/rooms").json() == []
    assert admin_client.post(f"/api/admin/actions/{action['id']}/undo").status_code == 409


def test_undo_refuses_later_edits_and_aba(admin_client):
    room = _post(admin_client, "/api/admin/rooms", {"name": "101", "building": "Г"})
    action = ledger(admin_client)[0]
    for name in ("102", "101"):
        assert admin_client.patch(f"/api/admin/rooms/{room['id']}", json={"name": name}).status_code == 200
    assert admin_client.post(f"/api/admin/actions/{action['id']}/undo").status_code == 409
    assert admin_client.get("/api/admin/rooms").json()[0]["name"] == "101"


def test_failed_mutation_has_no_action(admin_client):
    world = make_world(admin_client)
    count = len(ledger(admin_client))
    assert admin_client.delete(f"/api/admin/rooms/{world['room']['id']}").status_code == 409
    assert len(ledger(admin_client)) == count


def test_bulk_preview_cancel_and_atomic_undo(admin_client):
    world = make_world(admin_client)
    body = {
        "action": "cancel",
        "session_ids": [world["session"]["id"]],
        "date_from": "2026-11-09",
        "date_to": "2026-11-16",
        "comment": "Каникулы",
    }
    preview = admin_client.post("/api/admin/bulk", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["count"] == 2
    assert admin_client.get("/api/admin/exceptions").json() == []
    done = admin_client.post("/api/admin/bulk", json={**body, "preview": False, "confirmation": preview.json()["confirmation"]})
    assert done.status_code == 200, done.text
    assert len(admin_client.get("/api/admin/exceptions").json()) == 2
    action = ledger(admin_client)[0]
    assert admin_client.post(f"/api/admin/actions/{action['id']}/undo").status_code == 200
    assert admin_client.get("/api/admin/exceptions").json() == []


def test_bulk_stale_preview_and_missing_ids_do_not_write(admin_client):
    world = make_world(admin_client)
    body = {"action": "delete", "session_ids": [world["session"]["id"]]}
    preview = admin_client.post("/api/admin/bulk", json=body).json()
    admin_client.patch(f"/api/admin/sessions/{world['session']['id']}", json={"end_time": "11:10"})
    assert admin_client.post("/api/admin/bulk", json={**body, "preview": False, "confirmation": preview["confirmation"]}).status_code == 409
    assert admin_client.post("/api/admin/bulk", json={**body, "session_ids": [world["session"]["id"], 999999]}).status_code == 409
    assert len(admin_client.get("/api/admin/sessions").json()) == 1


def test_period_holidays_can_be_undone(admin_client):
    period = _post(
        admin_client,
        "/api/admin/periods",
        {"name": "Осень", "start_date": "2026-09-01", "end_date": "2026-12-31", "even_week_start": "2026-09-07"},
    )
    response = admin_client.post(
        f"/api/admin/periods/{period['id']}/days-off/range",
        json={"start_date": "2026-11-09", "end_date": "2026-11-11", "reason": "Каникулы"},
    )
    assert response.status_code in (200, 201), response.text
    action = ledger(admin_client)[0]
    assert admin_client.post(f"/api/admin/actions/{action['id']}/undo").status_code == 200
    assert admin_client.get(f"/api/admin/periods/{period['id']}/days-off").json() == []


def test_import_exact_preview_rolls_back_everything(admin_client):
    world = make_world(admin_client)
    draft = _post(
        admin_client,
        "/api/admin/imports",
        {
            "filename": "x.docx",
            "content_base64": docx(
                [["Кружок", "День", "Время", "Руководитель", "Аудитория"], ["Тест", "Вт", "12:00-13:00", "Иван", "101"]]
            ),
        },
    )
    choice = {
        "row": draft["rows"][0]["row"],
        "action": "create",
        "club_id": world["club"]["id"],
        "room_ids": [world["room"]["id"]],
        "weekday": 2,
        "start_time": "12:00",
        "end_time": "13:00",
        "repeat": "weekly",
    }
    assert admin_client.put(f"/api/admin/imports/{draft['id']}/decisions", json={"decisions": [choice]}).status_code == 200
    count = len(ledger(admin_client))
    preview = admin_client.post(f"/api/admin/imports/{draft['id']}/publish?dry_run=true")
    assert preview.status_code == 200, preview.text
    assert preview.json()["created"] == len(preview.json()["items"]) == 1
    assert len(admin_client.get("/api/admin/sessions").json()) == 1
    assert len(ledger(admin_client)) == count
    assert admin_client.get("/api/admin/imports").json()[0]["status"] == "draft"


def test_before_image_has_a_real_sqlite_write_reservation(admin_client, monkeypatch):
    from backend.app.services import import_journal

    capture = import_journal.capture
    reservations = []

    def checked(db):
        reservations.append(db.connection().connection.driver_connection.in_transaction)
        return capture(db)

    monkeypatch.setattr(import_journal, "capture", checked)
    response = admin_client.post("/api/admin/rooms", json={"name": "Atomic", "building": "Г"})
    assert response.status_code == 201, response.text
    assert reservations and all(reservations)


def test_journal_failure_never_commits_data_and_releases_reservation(admin_client, monkeypatch):
    from backend.app.services import import_journal

    original = import_journal.record

    def broken(*args, **kwargs):
        raise RuntimeError("fixture journal failure")

    monkeypatch.setattr(import_journal, "record", broken)
    response = admin_client.post("/api/admin/rooms", json={"name": "Never commit", "building": "Г"})
    assert response.status_code == 500
    assert admin_client.get("/api/admin/rooms").json() == []
    monkeypatch.setattr(import_journal, "record", original)
    assert admin_client.post("/api/admin/rooms", json={"name": "Recovered", "building": "Г"}).status_code == 201
