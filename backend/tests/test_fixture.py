import json
from pathlib import Path
from backend.app.schemas.contracts import ScheduleEvent

def test_mock_matches_source_and_event_schema():
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / "data/sample-data.json").read_text(encoding="utf-8"))
    assert source == json.loads((root / "frontend/mock-data.json").read_text(encoding="utf-8"))
    for event in source["schedule_events"]:
        ScheduleEvent.model_validate(event)
