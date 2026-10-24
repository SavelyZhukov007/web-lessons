from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.category import Category
from ..models.club import Club
from ..models.leader import Leader
from ..models.room import Room
from ..models.session import ClubSession
from ..models.session_exception import SessionException
from .clock import today_msk
from .conflicts import find_conflicts
from .schedule import build_week


@dataclass
class ProposedChange:
    operation: Literal[
        "create_session",
        "update_session",
        "create_cancel",
        "create_move",
        "delete_exception",
        "change_leader",
        "activate_club",
        "update_move",
        "update_club",
    ]
    entity_id: int | None
    payload: dict[str, Any]


class ScheduleConflictService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_proposed_state(
        self,
        change: ProposedChange,
    ) -> list[dict]:
        loaded_data = self._load_schedule_data()

        week_starts = self._get_affected_week_starts(
            loaded_data,
            change,
        )

        proposed_data = self._apply_proposed_change(
            loaded_data,
            change,
        )

        week_events = self._build_events(
            proposed_data,
            week_starts,
        )

        candidates = self._get_candidates(
            week_events,
            change,
            loaded_data,
        )

        events_by_id = {
            event["event_id"]: event
            for event in week_events
        }

        conflicts_by_id: dict[str, dict] = {}

        for candidate in candidates:
            candidate_conflicts = self._find_conflicts(
                candidate=candidate,
                events=week_events,
                exclude_event_id=candidate["event_id"],
            )

            for conflict in candidate_conflicts:
                event = events_by_id.get(conflict["event_id"])

                if event is None:
                    continue

                event_id = event["event_id"]

                if event_id not in conflicts_by_id:
                    conflicts_by_id[event_id] = {
                        "event_id": event_id,
                        "club_name": event["club_name"],
                        "date": event["date"],
                        "start_time": event["start_time"],
                        "end_time": event["end_time"],
                        "room_name": event["room_name"],
                        "leader_name": event["leader_name"],
                        "reasons": list(conflict["reasons"]),
                    }
                else:
                    existing_reasons = conflicts_by_id[event_id]["reasons"]

                    for reason in conflict["reasons"]:
                        if reason not in existing_reasons:
                            existing_reasons.append(reason)

        return list(conflicts_by_id.values())

    def _load_schedule_data(self) -> dict:
        categories = [
            {
                "id": category.id,
                "name": category.name,
                "color": category.color,
            }
            for category in self.db.execute(
                select(Category)
            ).scalars().all()
        ]

        leaders = [
            {
                "id": leader.id,
                "name": leader.name,
            }
            for leader in self.db.execute(
                select(Leader)
            ).scalars().all()
        ]

        rooms = [
            {
                "id": room.id,
                "name": room.name,
            }
            for room in self.db.execute(
                select(Room)
            ).scalars().all()
        ]

        clubs = [
            {
                "id": club.id,
                "name": club.name,
                "category_id": club.category_id,
                "leader_id": club.leader_id,
                "is_active": club.is_active,
            }
            for club in self.db.execute(
                select(Club)
            ).scalars().all()
        ]

        sessions = [
            {
                "id": session.id,
                "club_id": session.club_id,
                "room_id": session.room_id,
                "weekday": session.weekday,
                "start_time": session.start_time,
                "end_time": session.end_time,
            }
            for session in self.db.execute(
                select(ClubSession)
            ).scalars().all()
        ]

        session_exceptions = [
            {
                "id": exception.id,
                "session_id": exception.session_id,
                "original_date": exception.original_date,
                "type": exception.type,
                "comment": exception.comment or "",
                "new_date": exception.new_date,
                "new_room_id": exception.new_room_id,
                "new_start_time": exception.new_start_time,
                "new_end_time": exception.new_end_time,
            }
            for exception in self.db.execute(
                select(SessionException)
            ).scalars().all()
        ]

        return {
            "categories": categories,
            "leaders": leaders,
            "rooms": rooms,
            "clubs": clubs,
            "sessions": sessions,
            "session_exceptions": session_exceptions,
        }

    def _apply_proposed_change(
        self,
        data: dict,
        change: ProposedChange,
    ) -> dict:
        proposed_data = deepcopy(data)

        if change.operation == "create_session":
            proposed_data["sessions"].append(
                {
                    "id": change.entity_id,
                    "club_id": change.payload["club_id"],
                    "room_id": change.payload["room_id"],
                    "weekday": change.payload["weekday"],
                    "start_time": change.payload["start_time"],
                    "end_time": change.payload["end_time"],
                }
            )

        elif change.operation == "update_session":
            for session in proposed_data["sessions"]:
                if session["id"] == change.entity_id:
                    for key, value in change.payload.items():
                        session[key] = value

                    break

        elif change.operation == "create_cancel":
            proposed_data["session_exceptions"].append(
                {
                    "id": None,
                    "session_id": change.payload["session_id"],
                    "original_date": change.payload["original_date"],
                    "type": "cancelled",
                    "comment": change.payload.get("comment", ""),
                    "new_date": None,
                    "new_room_id": None,
                    "new_start_time": None,
                    "new_end_time": None,
                }
            )

        elif change.operation == "create_move":
            proposed_data["session_exceptions"].append(
                {
                    "id": None,
                    "session_id": change.payload["session_id"],
                    "original_date": change.payload["original_date"],
                    "type": "moved",
                    "comment": change.payload.get("comment", ""),
                    "new_date": change.payload["new_date"],
                    "new_room_id": change.payload["new_room_id"],
                    "new_start_time": change.payload["new_start_time"],
                    "new_end_time": change.payload["new_end_time"],
                }
            )

        elif change.operation == "update_move":
            for exception in proposed_data["session_exceptions"]:
                if exception["id"] != change.entity_id:
                    continue

                for key, value in change.payload.items():
                    if key in {"original_date", "new_date"}:
                        if isinstance(value, date):
                            value = value.isoformat()

                    exception[key] = value

                break

        elif change.operation == "delete_exception":
            proposed_data["session_exceptions"] = [
                exception
                for exception in proposed_data["session_exceptions"]
                if exception["id"] != change.entity_id
            ]

        elif change.operation == "change_leader":
            for club in proposed_data["clubs"]:
                if club["id"] == change.entity_id:
                    club["leader_id"] = change.payload["leader_id"]
                    break

        elif change.operation == "activate_club":
            for club in proposed_data["clubs"]:
                if club["id"] == change.entity_id:
                    club["is_active"] = True
                    break

        elif change.operation == "update_club":
            for club in proposed_data["clubs"]:
                if club["id"] != change.entity_id:
                    continue

                if "leader_id" in change.payload:
                    club["leader_id"] = change.payload["leader_id"]

                if "is_active" in change.payload:
                    club["is_active"] = change.payload["is_active"]

                break

        return proposed_data

    def _get_affected_week_starts(
        self,
        data: dict,
        change: ProposedChange,
    ) -> set[date]:
        def get_week_start(target_date: date) -> date:
            return target_date - timedelta(
                days=target_date.weekday()
            )

        def normalize_date(value: date | str) -> date:
            if isinstance(value, str):
                return date.fromisoformat(value)

            return value

        affected_weeks: set[date] = set()

        if change.operation in {
            "create_cancel",
            "create_move",
        }:
            original_date = normalize_date(
                change.payload["original_date"]
            )

            affected_weeks.add(
                get_week_start(original_date)
            )

        if change.operation == "create_move":
            new_date = normalize_date(
                change.payload["new_date"]
            )

            affected_weeks.add(
                get_week_start(new_date)
            )

        elif change.operation == "delete_exception":
            for exception in data["session_exceptions"]:
                if exception["id"] != change.entity_id:
                    continue

                original_date = normalize_date(
                    exception["original_date"]
                )

                affected_weeks.add(
                    get_week_start(original_date)
                )

                if (
                    exception["type"] == "moved"
                    and exception["new_date"] is not None
                ):
                    new_date = normalize_date(
                        exception["new_date"]
                    )

                    affected_weeks.add(
                        get_week_start(new_date)
                    )

                break

        elif change.operation == "update_move":
            for exception in data["session_exceptions"]:
                if exception["id"] != change.entity_id:
                    continue

                # Недели до изменения
                old_original_date = normalize_date(exception["original_date"])
                affected_weeks.add(get_week_start(old_original_date))

                if exception["new_date"] is not None:
                    old_new_date = normalize_date(exception["new_date"])
                    affected_weeks.add(get_week_start(old_new_date))

                # Недели после изменения
                new_original_date = normalize_date(
                    change.payload.get("original_date", exception["original_date"])
                )
                affected_weeks.add(get_week_start(new_original_date))

                new_date_value = change.payload.get(
                    "new_date", exception["new_date"]
                )
                if new_date_value is not None:
                    new_date = normalize_date(new_date_value)
                    affected_weeks.add(get_week_start(new_date))

                break

        regular_operations = {
            "create_session",
            "update_session",
            "change_leader",
            "activate_club",
            "update_club",
        }

        if change.operation in regular_operations:
            exception_dates: set[date] = set()

            for exception in data["session_exceptions"]:
                exception_dates.add(
                    normalize_date(exception["original_date"])
                )

                if exception["new_date"] is not None:
                    exception_dates.add(
                        normalize_date(exception["new_date"])
                    )

            today = today_msk()
            normal_week_start = get_week_start(today) + timedelta(days=7)

            while any(
                normal_week_start
                <= exception_date
                <= normal_week_start + timedelta(days=6)
                for exception_date in exception_dates
            ):
                normal_week_start += timedelta(days=7)

            affected_weeks.add(normal_week_start)

            for exception_date in exception_dates:
                if exception_date >= today:
                    affected_weeks.add(
                    get_week_start(exception_date)
                    )
        return affected_weeks

    def _build_events(
        self,
        proposed_data: dict,
        week_starts: set[date],
    ) -> list[dict]:
        events: list[dict] = []

        for week_start in week_starts:
            week_events = build_week(
                week_start,
                proposed_data,
            )

            events.extend(week_events)

        return events

    def _get_candidates(
        self,
        events: list[dict],
        change: ProposedChange,
        original_data: dict,
    ) -> list[dict]:
        if change.operation == "create_cancel":
            return []

        if change.operation in {
            "create_session",
            "update_session",
        }:
            return [
                event
                for event in events
                if (
                    event["session_id"] == change.entity_id
                    and event["status"] != "cancelled"
                )
            ]

        if change.operation == "create_move":
            original_date = change.payload["original_date"]

            if isinstance(original_date, date):
                original_date = original_date.isoformat()

            return [
                event
                for event in events
                if (
                    event["session_id"] == change.payload["session_id"]
                    and event["status"] == "moved"
                    and event["original_date"] == original_date
                )
            ]

        if change.operation in {
            "change_leader",
            "activate_club",
            "update_club",
        }:
            return [
                event
                for event in events
                if (
                    event["club_id"] == change.entity_id
                    and event["status"] != "cancelled"
                )
            ]

        if change.operation == "update_move":
            exception = next(
                (
                    item
                    for item in original_data["session_exceptions"]
                    if item["id"] == change.entity_id
                ),
                None,
            )

            if exception is None:
                return []

            new_session_id = change.payload.get(
                "session_id", exception["session_id"]
            )
            new_original_date = change.payload.get(
                "original_date", exception["original_date"]
            )

            if isinstance(new_original_date, date):
                new_original_date = new_original_date.isoformat()

            candidates = [
                event
                for event in events
                if (
                    event["session_id"] == new_session_id
                    and event["original_date"] == new_original_date
                    and event["status"] == "moved"
                )
            ]

            old_original_date = exception["original_date"]

            if (
                exception["session_id"] != new_session_id
                or old_original_date != new_original_date
            ):
                candidates.extend(
                    event
                    for event in events
                    if (
                        event["session_id"] == exception["session_id"]
                        and event["original_date"] == old_original_date
                        and event["status"] != "cancelled"
                    )
                )

            return candidates

        if change.operation == "delete_exception":
            exception = next(
                (
                    item
                    for item in original_data["session_exceptions"]
                    if item["id"] == change.entity_id
                ),
                None,
            )

            if exception is None:
                return []

            return [
                event
                for event in events
                if (
                    event["session_id"] == exception["session_id"]
                    and event["original_date"] == exception["original_date"]
                    and event["status"] != "cancelled"
                )
            ]

        return []

    def _find_conflicts(
        self,
        candidate: dict,
        events: list[dict],
        exclude_event_id: str | None = None,
    ) -> list[dict]:
        return find_conflicts(
            candidate,
            events,
            exclude_event_id,
        )
