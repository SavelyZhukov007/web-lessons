"""QA-07: tools/validate_data.py — ненулевой код выхода на битых данных, UTF-8, ссылочная целостность."""
import json
from pathlib import Path

from tools.validate_data import main, validate

ROOT = Path(__file__).resolve().parents[2]


def _good():
    return json.loads((ROOT / "data" / "demo-data.json").read_text(encoding="utf-8"))


def test_demo_data_is_valid():
    assert validate(_good()) == []
    assert main([str(ROOT / "data" / "demo-data.json")]) == 0


def test_duplicate_ids_and_broken_references_fail(tmp_path, capsys):
    data = _good()
    data["rooms"].append(dict(data["rooms"][0]))
    data["sessions"][0]["club_id"] = 9999
    data["sessions"][1]["weekday"] = 7
    data["sessions"][2]["start_time"], data["sessions"][2]["end_time"] = "18:00", "17:00"
    data["clubs"][0]["leader_id"] = 4242
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert main([str(path)]) == 1
    out = capsys.readouterr().out
    for fragment in ("повторяющийся id", "club_id = 9999", "weekday = 7", "не раньше", "leader_id = 4242"):
        assert fragment in out


def test_unreadable_or_non_json_file_exits_2(tmp_path):
    assert main([str(tmp_path / "nope.json")]) == 2
    bad = tmp_path / "x.json"
    bad.write_text("{не json", encoding="utf-8")
    assert main([str(bad)]) == 2
