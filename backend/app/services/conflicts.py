"""Эдик и Максим. Чистые функции: без FastAPI, БД, сетевых запросов."""
from datetime import time

def intervals_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    """TODO: проверка интервалов. Соседние границы НЕ пересекаются."""
    raise NotImplementedError("Задача 4: реализовать пересечение интервалов")

def find_conflicts(candidate: dict, events: list[dict], exclude_event_id: str | None = None) -> list[dict]:
    """Вход: события из контракта. Выход: [{event_id, reasons: [room, leader]}].
    Отменённые пропустить; сравнивать дату, действующие время и room_id.
    При редактировании исключать конкретное событие, не всю серию session_id.
    """
    raise NotImplementedError("Задача 4: реализовать проверку конфликтов")
