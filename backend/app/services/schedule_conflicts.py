from copy import deepcopy
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.category import Category
from ..models.leader import Leader
from ..models.room import Room
from ..models.club import Club
from ..models.session import ClubSession
from ..models.session_exception import SessionException

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
        )

        conflicts: list[dict] = []

        for candidate in candidates:
            candidate_conflicts = self._find_conflicts(
                candidate=candidate,
                events=week_events,
                exclude_event_id=candidate["event_id"],
            )

            conflicts.extend(candidate_conflicts)

        return conflicts

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
                "original_date": exception.original_date.isoformat(),
                "type": exception.type,
                "comment": exception.comment or "",
                "new_date": (
                    exception.new_date.isoformat()
                    if exception.new_date is not None
                    else None
                ),
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
    ) -> list[dict]:
        if change.operation in {
            "create_session",
            "update_session",
        }:
            return [
                event
                for event in events
                if event["session_id"] == change.entity_id
            ]

        if change.operation == "create_move":
            original_date = change.payload["original_date"]

            if isinstance(original_date, date):
                original_date = original_date.isoformat()

            return [
                event
                for event in events
                if (
                    event["session_id"]
                    == change.payload["session_id"]
                    and event["status"] == "moved"
                    and event["original_date"] == original_date
                )
            ]

        if change.operation in {
            "change_leader",
            "activate_club",
        }:
            return [
                event
                for event in events
                if event["club_id"] == change.entity_id
            ]

        if change.operation == "delete_exception":
            return [
                event
                for event in events
                if event["status"] != "cancelled"
            ]

        if change.operation == "create_cancel":
            return []

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