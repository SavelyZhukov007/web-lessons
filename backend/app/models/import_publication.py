"""SQLite journal for schedule imports and row revisions for safe undo."""
from sqlalchemy import DDL, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# Parent tables precede their children. Undo deletes in the opposite order.
SCHEDULE_KEYS = {
    "categories": ("id",),
    "leaders": ("id",),
    "rooms": ("id",),
    "clubs": ("id",),
    "academic_periods": ("id",),
    "no_class_days": ("id",),
    "sessions": ("id",),
    "club_leaders": ("club_id", "leader_id"),
    "session_leaders": ("session_id", "leader_id"),
    "session_rooms": ("session_id", "room_id"),
    "session_exceptions": ("id",),
}


class ImportPublication(Base):
    __tablename__ = "import_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String)
    draft_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    metadata_json: Mapped[str] = mapped_column(Text)
    changes_json: Mapped[str] = mapped_column(Text)
    rolled_back: Mapped[bool] = mapped_column(default=False)


class ScheduleRowRevision(Base):
    __tablename__ = "schedule_row_revisions"

    table_name: Mapped[str] = mapped_column(String, primary_key=True)
    row_key: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[str] = mapped_column(String)


def revision_triggers():
    for table, columns in SCHEDULE_KEYS.items():
        def record(row, table=table, columns=columns):
            key = ", ".join(f"{row}.{column}" for column in columns)
            return f"""
                INSERT INTO schedule_row_revisions VALUES ('{table}', json_array({key}), hex(randomblob(16)))
                ON CONFLICT (table_name, row_key) DO UPDATE SET revision = excluded.revision;
            """

        for operation, rows in (("insert", ("NEW",)), ("update", ("OLD", "NEW")), ("delete", ("OLD",))):
            name = f"schedule_revision_{table}_{operation}"
            yield name, f"CREATE TRIGGER IF NOT EXISTS {name} AFTER {operation} ON {table} BEGIN {''.join(map(record, rows))} END"


for _, statement in revision_triggers():
    event.listen(Base.metadata, "after_create", DDL(statement))
