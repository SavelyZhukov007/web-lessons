from datetime import time

from backend.app.services.conflicts import intervals_overlap


def test_adjacent_intervals_do_not_overlap():
    assert not intervals_overlap(time(10), time(11), time(11), time(12))


def test_overlapping_and_nested_intervals_overlap():
    assert intervals_overlap(time(10), time(11, 30), time(11), time(12))
    assert intervals_overlap(time(10), time(14), time(11), time(12))
    assert intervals_overlap(time(11), time(12), time(10), time(14))
