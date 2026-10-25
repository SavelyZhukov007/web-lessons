"""Логика зон и авто-стопа стресс-теста (tools/stress/stress_test.py) — без сети."""
from tools.stress.stress_test import Audience, Thresholds, classify, is_local, percentile, should_stop

T = Thresholds()


def test_zones():
    assert classify(120, 0.0, T) == "comfort"
    assert classify(300, 0.001, T) == "comfort"
    assert classify(301, 0.0, T) == "normal"
    assert classify(200, 0.005, T) == "normal"
    assert classify(999, 0.0099, T) == "normal"
    assert classify(1001, 0.0, T) == "overload"
    assert classify(100, 0.01, T) == "overload"


def test_autostop():
    assert not should_stop(1500, 0.02, T)
    assert should_stop(2500, 0.0, T)
    assert should_stop(100, 0.06, T)


def test_percentile_and_audience():
    assert percentile([], 95) == 0
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    est = Audience(session_min=5, sessions_per_day=2, peak_hour_share=0.25).estimate(100)
    assert est == {"peak_hour_users": 1200, "daily_users": 2400}


def test_prod_guard():
    assert is_local("http://127.0.0.1:8000")
    assert not is_local("http://lekora.ru:7443")
