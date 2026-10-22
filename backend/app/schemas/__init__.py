"""Часть шаблона проекта. Назначение описано в docs/START_HERE.md."""

from .admin import AdminLoginRequest, AdminStatusResponse, AdminSummary
from .category import CategoryCreate, CategoryRead, CategoryUpdate
from .club import ClubCreate, ClubDetailRead, ClubRead, ClubUpdate
from .contracts import ScheduleEvent
from .leader import LeaderCreate, LeaderRead, LeaderUpdate
from .room import RoomCreate, RoomRead, RoomUpdate
from .session import SessionCreate, SessionRead, SessionUpdate, SessionWithRoomRead
from .session_exception import (
    CancellationCreate,
    CancellationUpdate,
    MoveCreate,
    MoveUpdate,
    SessionExceptionRead,
)

__all__ = [
    "AdminLoginRequest",
    "AdminStatusResponse",
    "AdminSummary",
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    "ClubCreate",
    "ClubDetailRead",
    "ClubRead",
    "ClubUpdate",
    "LeaderCreate",
    "LeaderRead",
    "LeaderUpdate",
    "RoomCreate",
    "RoomRead",
    "RoomUpdate",
    "ScheduleEvent",
    "SessionCreate",
    "SessionRead",
    "SessionUpdate",
    "SessionWithRoomRead",
    "CancellationCreate",
    "CancellationUpdate",
    "MoveCreate",
    "MoveUpdate",
    "SessionExceptionRead",
]
