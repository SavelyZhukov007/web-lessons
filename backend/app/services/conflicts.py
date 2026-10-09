"""Эдик и Максим. Чистые функции: без FastAPI, БД, сетевых запросов."""
from datetime import date, time

def intervals_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    """TODO: проверка интервалов. Соседние границы НЕ пересекаются."""
    raise NotImplementedError("Задача 4: реализовать пересечение интервалов")


def find_conflicts(candidate: dict, events: list[dict], exclude_event_id: str | None = None) -> list[dict]:
    """Вход: события из контракта. Выход: [{event_id, reasons: [room, leader]}].
    Отменённые пропустить; сравнивать дату, действующие время и room_id.
    При редактировании исключать конкретное событие, не всю серию session_id.
    """
    conflicts = []
    for event in events:
        reasons = []
        if event["event_id"] == exclude_event_id:
            continue

        if event["status"] == "cancelled":
            continue

        if candidate["date"] != event["date"]:
            continue
        
        time_check = intervals_overlap(
            candidate["start_time"],
            candidate["end_time"],
            event["start_time"],
            event["end_time"],
        )
        
        if not time_check:
            continue

        if candidate["room_id"] == event["room_id"]:
            reasons.append("room")

        if candidate["leader_id"] == event["leader_id"]:
            reasons.append("leader")

        if reasons:
            conflicts.append({
                "event_id": event["event_id"],
                "reasons" : reasons,
            })
        
    return conflicts





    