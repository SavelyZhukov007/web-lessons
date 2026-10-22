from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    Response,
    status as http_status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth import (
    generate_session_token,
    hash_session_token,
    normalize_login,
    verify_password,
)
from ..database import get_db
from ..models.admin import Admin, AdminSession
from ..models.category import Category
from ..models.club import Club
from ..models.leader import Leader
from ..models.room import Room
from ..models.session import ClubSession
from ..models.session_exception import SessionException
from ..schemas.admin import AdminLoginRequest, AdminStatusResponse
from ..schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from ..schemas.club import ClubCreate, ClubRead, ClubUpdate
from ..schemas.leader import LeaderCreate, LeaderRead, LeaderUpdate
from ..schemas.room import RoomCreate, RoomRead, RoomUpdate
from ..schemas.session import SessionCreate, SessionRead, SessionUpdate
from ..schemas.session_exception import (
    CancellationCreate,
    CancellationUpdate,
    MoveCreate,
    MoveUpdate,
    SessionExceptionRead,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

COOKIE_NAME = "admin_session"
SESSION_LIFETIME = timedelta(days=7)

login_attempts_by_ip: dict[str, dict] = {}

# {
#     "123": {
#         "attempts": 0,
#         "locked_until": None
#     },
#     "456": {
#         "attempts": 5,
#         "locked_until": datetime('whatever...')
#     }
# }

MAX_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=5)


def _check_ip(ip: str) -> None:
    record = login_attempts_by_ip.get(ip)
    if record is None:
        return

    locked_until = record.get("locked_until")
    if locked_until is None:
        return

    utcnow = _utcnow()
    if locked_until > utcnow:
        remaining = int((locked_until - utcnow).total_seconds())
        raise HTTPException(
            status_code=429, 
            detail=f"Слишком много неудачных попыток входа. Попробуйте через {remaining} секунд.", 
            headers={"Retry-After": str(remaining)}
        )
    else:
        _remove_ip(ip)


def _add_failed_attempt(ip: str) -> None:
    record = login_attempts_by_ip.get(ip)

    if record is None:
        login_attempts_by_ip[ip] = {
            "attempts": 0,
            "locked_until": None
        }
        record = login_attempts_by_ip[ip]

    record["attempts"] += 1

    if record["attempts"] >= MAX_ATTEMPTS:
        record["locked_until"] = _utcnow() + LOCK_DURATION


def _remove_ip(ip: str) -> None:
    login_attempts_by_ip.pop(ip, None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_admin_session(request: Request, db: Session) -> AdminSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Требуется вход администратора")

    admin_session = db.scalar(
        select(AdminSession)
        .where(AdminSession.token_hash == hash_session_token(token))
        .join(AdminSession.admin)
    )
    if admin_session is None:
        raise HTTPException(401, "Требуется вход администратора")

    if admin_session.expires_at <= _utcnow():
        db.delete(admin_session)
        db.commit()
        raise HTTPException(401, "Сессия администратора истекла, войдите снова")

    return admin_session


def require_admin_session(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminSession:
    return _get_admin_session(request, db)


def require_admin(
    admin_session: AdminSession = Depends(require_admin_session),
) -> Admin:
    return admin_session.admin


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _commit_or_raise_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail) from exc


def _normalize_login_or_422(login: str) -> str:
    try:
        return normalize_login(login)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _get_or_404(db: Session, model, item_id: int, detail: str):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, detail)
    return item


def _category_exists(db: Session, category_id: int) -> None:
    if db.get(Category, category_id) is None:
        raise HTTPException(404, "Направление не найдено")


def _leader_exists(db: Session, leader_id: int) -> None:
    if db.get(Leader, leader_id) is None:
        raise HTTPException(404, "Руководитель не найден")


def _room_exists(db: Session, room_id: int) -> None:
    if db.get(Room, room_id) is None:
        raise HTTPException(404, "Аудитория не найдена")


def _club_exists(db: Session, club_id: int) -> None:
    if db.get(Club, club_id) is None:
        raise HTTPException(404, "Кружок не найден")


def _session_exists(db: Session, session_id: int) -> None:
    if db.get(ClubSession, session_id) is None:
        raise HTTPException(404, "Регулярное занятие не найдено")


def _apply_model_updates(item, payload) -> None:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)


def _validate_interval(start_time: str, end_time: str, detail: str) -> None:
    if start_time >= end_time:
        raise HTTPException(422, detail)


def _prepare_exception_payload(payload) -> dict:
    data = payload.model_dump()
    if data["type"] == "cancelled":
        data["original_date"] = data["original_date"].isoformat()
        data["comment"] = data["comment"]
        return {
            "session_id": data["session_id"],
            "original_date": data["original_date"],
            "type": data["type"],
            "comment": data["comment"],
            "new_date": None,
            "new_start_time": None,
            "new_end_time": None,
            "new_room_id": None,
        }
    return {
        "session_id": data["session_id"],
        "original_date": data["original_date"].isoformat(),
        "type": data["type"],
        "new_date": data["new_date"].isoformat(),
        "new_start_time": data["new_start_time"],
        "new_end_time": data["new_end_time"],
        "new_room_id": data["new_room_id"],
        "comment": data["comment"],
    }


def _prepare_exception_patch(existing: SessionException, payload_model) -> dict:
    updates = payload_model.model_dump(exclude_unset=True)
    prepared: dict = {}
    for field, value in updates.items():
        if field in {"original_date", "new_date"} and value is not None:
            prepared[field] = value.isoformat()
        else:
            prepared[field] = value

    if existing.type == "cancelled":
        prepared.update(
            {
                "type": "cancelled",
                "new_date": None,
                "new_start_time": None,
                "new_end_time": None,
                "new_room_id": None,
            }
        )
    elif "type" in prepared and prepared["type"] != "moved":
        raise HTTPException(422, "Тип исключения нельзя менять")

    return prepared


def _load_exception_patch(existing: SessionException, payload: dict):
    if existing.type == "cancelled":
        return CancellationUpdate.model_validate(payload)
    return MoveUpdate.model_validate(payload)


@router.post("/login", response_model=AdminStatusResponse)
def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else ""
    _check_ip(ip)

    login_name = _normalize_login_or_422(payload.login)
    admin = db.scalar(select(Admin).where(Admin.login == login_name))

    if admin is None or not verify_password(payload.password, admin.password_hash):
        _add_failed_attempt(ip)
        raise HTTPException(401, "Неверный логин или пароль")

    _remove_ip(ip)
    
    token = generate_session_token()
    db.add(
        AdminSession(
            admin_id=admin.id,
            token_hash=hash_session_token(token),
            expires_at=_utcnow() + SESSION_LIFETIME,
        )
    )
    _commit_or_raise_conflict(db, "Не удалось создать сессию администратора")
    _set_session_cookie(response, token)
    return {"admin": admin}


@router.post("/logout", status_code=http_status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    admin_session: AdminSession = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    db.delete(admin_session)
    db.commit()
    _clear_session_cookie(response)


@router.get("/status", response_model=AdminStatusResponse)
def get_status(current_admin: Admin = Depends(require_admin)):
    return {"admin": current_admin}


@router.get(
    "/categories",
    response_model=list[CategoryRead],
    dependencies=[Depends(require_admin)],
)
def list_categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name, Category.id)))


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    category = Category(**payload.model_dump())
    db.add(category)
    _commit_or_raise_conflict(db, "Не удалось сохранить направление")
    db.refresh(category)
    return category


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(require_admin)],
)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
):
    category = _get_or_404(db, Category, category_id, "Направление не найдено")
    _apply_model_updates(category, payload)
    _commit_or_raise_conflict(db, "Не удалось обновить направление")
    db.refresh(category)
    return category


@router.delete(
    "/categories/{category_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = _get_or_404(db, Category, category_id, "Направление не найдено")
    has_clubs = db.scalar(
        select(Club.id).where(Club.category_id == category_id).limit(1)
    )
    if has_clubs is not None:
        raise HTTPException(
            409, "Нельзя удалить направление, пока к нему привязаны кружки"
        )
    db.delete(category)
    db.commit()


@router.get(
    "/leaders", response_model=list[LeaderRead], dependencies=[Depends(require_admin)]
)
def list_leaders(db: Session = Depends(get_db)):
    return list(db.scalars(select(Leader).order_by(Leader.name, Leader.id)))


@router.post(
    "/leaders",
    response_model=LeaderRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_leader(payload: LeaderCreate, db: Session = Depends(get_db)):
    leader = Leader(**payload.model_dump())
    db.add(leader)
    db.commit()
    db.refresh(leader)
    return leader


@router.patch(
    "/leaders/{leader_id}",
    response_model=LeaderRead,
    dependencies=[Depends(require_admin)],
)
def update_leader(leader_id: int, payload: LeaderUpdate, db: Session = Depends(get_db)):
    leader = _get_or_404(db, Leader, leader_id, "Руководитель не найден")
    _apply_model_updates(leader, payload)
    db.commit()
    db.refresh(leader)
    return leader


@router.delete(
    "/leaders/{leader_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_leader(leader_id: int, db: Session = Depends(get_db)):
    leader = _get_or_404(db, Leader, leader_id, "Руководитель не найден")
    has_clubs = db.scalar(select(Club.id).where(Club.leader_id == leader_id).limit(1))
    if has_clubs is not None:
        raise HTTPException(
            409, "Нельзя удалить руководителя, пока к нему привязаны кружки"
        )
    db.delete(leader)
    db.commit()


@router.get(
    "/rooms", response_model=list[RoomRead], dependencies=[Depends(require_admin)]
)
def list_rooms(db: Session = Depends(get_db)):
    return list(db.scalars(select(Room).order_by(Room.building, Room.name, Room.id)))


@router.post(
    "/rooms",
    response_model=RoomRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    room = Room(**payload.model_dump())
    db.add(room)
    _commit_or_raise_conflict(db, "Не удалось сохранить аудиторию")
    db.refresh(room)
    return room


@router.patch(
    "/rooms/{room_id}", response_model=RoomRead, dependencies=[Depends(require_admin)]
)
def update_room(room_id: int, payload: RoomUpdate, db: Session = Depends(get_db)):
    room = _get_or_404(db, Room, room_id, "Аудитория не найдена")
    _apply_model_updates(room, payload)
    _commit_or_raise_conflict(db, "Не удалось обновить аудиторию")
    db.refresh(room)
    return room


@router.delete(
    "/rooms/{room_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_room(room_id: int, db: Session = Depends(get_db)):
    room = _get_or_404(db, Room, room_id, "Аудитория не найдена")
    has_sessions = db.scalar(
        select(ClubSession.id).where(ClubSession.room_id == room_id).limit(1)
    )
    if has_sessions is not None:
        raise HTTPException(
            409, "Нельзя удалить аудиторию, пока в ней есть регулярные занятия"
        )
    has_moves = db.scalar(
        select(SessionException.id)
        .where(SessionException.new_room_id == room_id)
        .limit(1)
    )
    if has_moves is not None:
        raise HTTPException(
            409, "Нельзя удалить аудиторию, пока на неё есть переносы занятий"
        )
    db.delete(room)
    db.commit()


@router.get(
    "/clubs", response_model=list[ClubRead], dependencies=[Depends(require_admin)]
)
def list_clubs(db: Session = Depends(get_db)):
    return list(db.scalars(select(Club).order_by(Club.name, Club.id)))


@router.post(
    "/clubs",
    response_model=ClubRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_club(payload: ClubCreate, db: Session = Depends(get_db)):
    _category_exists(db, payload.category_id)
    _leader_exists(db, payload.leader_id)
    club = Club(**payload.model_dump())
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


@router.patch(
    "/clubs/{club_id}", response_model=ClubRead, dependencies=[Depends(require_admin)]
)
def update_club(club_id: int, payload: ClubUpdate, db: Session = Depends(get_db)):
    club = _get_or_404(db, Club, club_id, "Кружок не найден")
    updates = payload.model_dump(exclude_unset=True)
    if "category_id" in updates:
        _category_exists(db, updates["category_id"])
    if "leader_id" in updates:
        _leader_exists(db, updates["leader_id"])
    _apply_model_updates(club, payload)
    db.commit()
    db.refresh(club)
    return club


@router.delete(
    "/clubs/{club_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_club(club_id: int, db: Session = Depends(get_db)):
    club = _get_or_404(db, Club, club_id, "Кружок не найден")
    db.delete(club)
    db.commit()


@router.get(
    "/sessions", response_model=list[SessionRead], dependencies=[Depends(require_admin)]
)
def list_sessions(db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(ClubSession).order_by(
                ClubSession.weekday, ClubSession.start_time, ClubSession.id
            )
        )
    )


@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    _club_exists(db, payload.club_id)
    _room_exists(db, payload.room_id)
    session = ClubSession(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionRead,
    dependencies=[Depends(require_admin)],
)
def update_session(
    session_id: int, payload: SessionUpdate, db: Session = Depends(get_db)
):
    session = _get_or_404(db, ClubSession, session_id, "Регулярное занятие не найдено")
    updates = payload.model_dump(exclude_unset=True)
    if "club_id" in updates:
        _club_exists(db, updates["club_id"])
    if "room_id" in updates:
        _room_exists(db, updates["room_id"])
    if ("start_time" in updates) ^ ("end_time" in updates):
        updates["start_time"] = updates.get("start_time", session.start_time)
        updates["end_time"] = updates.get("end_time", session.end_time)
        _validate_interval(
            updates["start_time"],
            updates["end_time"],
            "Начало занятия должно быть раньше конца",
        )
        for field, value in updates.items():
            setattr(session, field, value)
    else:
        _apply_model_updates(session, payload)
    db.commit()
    db.refresh(session)
    return session


@router.delete(
    "/sessions/{session_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = _get_or_404(db, ClubSession, session_id, "Регулярное занятие не найдено")
    db.delete(session)
    db.commit()


@router.get(
    "/exceptions",
    response_model=list[SessionExceptionRead],
    dependencies=[Depends(require_admin)],
)
def list_exceptions(db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(SessionException).order_by(
                SessionException.original_date,
                SessionException.id,
            )
        )
    )


@router.post(
    "/exceptions/cancellations",
    response_model=SessionExceptionRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_cancellation(payload: CancellationCreate, db: Session = Depends(get_db)):
    _session_exists(db, payload.session_id)
    exception = SessionException(**_prepare_exception_payload(payload))
    db.add(exception)
    _commit_or_raise_conflict(db, "Не удалось сохранить отмену занятия")
    db.refresh(exception)
    return exception


@router.post(
    "/exceptions/moves",
    response_model=SessionExceptionRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_move(payload: MoveCreate, db: Session = Depends(get_db)):
    _session_exists(db, payload.session_id)
    _room_exists(db, payload.new_room_id)
    exception = SessionException(**_prepare_exception_payload(payload))
    db.add(exception)
    _commit_or_raise_conflict(db, "Не удалось сохранить перенос занятия")
    db.refresh(exception)
    return exception


@router.patch(
    "/exceptions/{exception_id}",
    response_model=SessionExceptionRead,
    dependencies=[Depends(require_admin)],
)
def update_exception(
    exception_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    exception = _get_or_404(
        db, SessionException, exception_id, "Исключение занятия не найдено"
    )
    patch_model = _load_exception_patch(exception, payload)
    updates = _prepare_exception_patch(exception, patch_model)
    if "session_id" in updates and updates["session_id"] is not None:
        _session_exists(db, updates["session_id"])
    if "new_room_id" in updates and updates["new_room_id"] is not None:
        _room_exists(db, updates["new_room_id"])
    if exception.type == "moved" and (
        "new_start_time" in updates or "new_end_time" in updates
    ):
        _validate_interval(
            updates.get("new_start_time", exception.new_start_time),
            updates.get("new_end_time", exception.new_end_time),
            "Начало переноса должно быть раньше конца",
        )
    for field, value in updates.items():
        setattr(exception, field, value)
    _commit_or_raise_conflict(db, "Не удалось обновить исключение занятия")
    db.refresh(exception)
    return exception


@router.delete(
    "/exceptions/{exception_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_exception(exception_id: int, db: Session = Depends(get_db)):
    exception = _get_or_404(
        db, SessionException, exception_id, "Исключение занятия не найдено"
    )
    db.delete(exception)
    db.commit()
