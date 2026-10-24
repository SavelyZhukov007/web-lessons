import json
from pathlib import Path

from backend.app.schemas.contracts import ScheduleEvent


def test_sample_data_matches_event_schema():
    """Демо-данные (источник для seed) валидны по схеме событий; браузерного мока больше нет (PUB-07)."""
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / "data/sample-data.json").read_text(encoding="utf-8"))
    assert not (root / "frontend/mock-data.json").exists()
    for event in source["schedule_events"]:
        ScheduleEvent.model_validate(event)
