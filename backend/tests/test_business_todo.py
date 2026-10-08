"""Алиса Жукова: заменить skip реальными тестами по мере реализации.
Не считать пропущенные тесты подтверждением готовности бизнес-логики.
"""
import pytest

@pytest.mark.skip(reason="TODO задача 4: функции ещё не реализованы")
def test_adjacent_intervals_do_not_overlap():
    from datetime import time
    from backend.app.services.conflicts import intervals_overlap
    assert not intervals_overlap(time(10), time(11), time(11), time(12))

@pytest.mark.skip(reason="TODO задача 5: сервис ещё не реализован")
def test_schedule_cases():
    # Добавить отдельные тесты отмен, переносов, неактивных кружков.
    raise NotImplementedError
