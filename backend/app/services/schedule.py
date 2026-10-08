"""Фёдор: формирование недели. Без API и БД; результат соответствует ScheduleEvent."""
from datetime import date

def build_week(week_start: date, data: dict) -> list[dict]:
    """TODO: раскрыть sessions в события, применить session_exceptions.
    Принимать понедельник. Исключить неактивные кружки.
    Отмена видна со статусом cancelled, но не занимает время.
    Перенос: moved на новом месте; оригинал не считать действующим.
    Добавить переносы из других недель. Сортировать по дате и времени.
    Формат data — data/sample-data.json. Не мутировать входные данные.
    """
    raise NotImplementedError("Задача 5: реализовать расписание недели")
