"""Record schedule CRUD in its original transaction, with row-revision-safe undo."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from . import import_journal

RESOURCES = {
    "categories": "Категории",
    "leaders": "Руководители",
    "rooms": "Аудитории",
    "clubs": "Кружки",
    "sessions": "Занятия",
    "exceptions": "Изменения расписания",
    "periods": "Учебные периоды",
    "bulk": "Пакетное изменение",
    "calendar": "Перенос в календаре",
}
VERBS = {"POST": "Создание", "PATCH": "Изменение", "PUT": "Изменение", "DELETE": "Удаление"}


def listen(db: Session, request, author: str):
    parts = request.url.path.strip("/").split("/")
    resource = parts[2] if len(parts) > 2 else ""
    if request.method not in VERBS or resource not in RESOURCES:
        return lambda: None
    # Reserve SQLite before the before-image too: CLI/other connections cannot leak edits into this action.
    import_journal.begin(db)
    before = import_journal.capture(db)
    recorded = False

    def before_commit(session):
        nonlocal recorded
        if recorded or import_journal.capture(session) == before:
            return
        import_journal.record(
            session,
            before,
            author=author,
            stats={},
            metadata={
                "kind": "action",
                "label": f"{VERBS[request.method]} · {RESOURCES[resource]}",
                "request_id": getattr(request.state, "request_id", request.headers.get("X-Request-ID", "")),
                "method": request.method,
                "path": request.url.path,
            },
        )
        recorded = True

    event.listen(db, "before_commit", before_commit)

    def cleanup():
        event.remove(db, "before_commit", before_commit)
        # A preview or a rejected mutation releases its SQLite reservation before the async API lock.
        if db.in_transaction():
            db.rollback()

    return cleanup
