from __future__ import annotations

import asyncio
import hmac
import weakref
from datetime import date, datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Request,
    Response,
)
from fastapi import (
    status as http_status,
)
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import settings
from ..auth import (
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_login,
    validate_password,
    verify_dummy,
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
from ..schemas.admin import AdminLoginRequest, AdminStatusResponse, LoginResponse, PasswordChangeRequest, RefreshRequest
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
from ..services import audit, login_limiter
from ..services.push import notify_exception
from ..services.schedule_conflicts import (
    ProposedChange,
    ScheduleConflictService,
)
from ..services.tokens import decode_token, issue_token

router = APIRouter(prefix="/api/admin", tags=["admin"])

def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


COOKIE_NAME = "admin_session"
REFRESH_COOKIE = "admin_refresh"
REFRESH_PATH = "/api/admin/refresh"
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _bearer_or_cookie_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return request.cookies.get(COOKIE_NAME)


def _get_admin_session(request: Request, db: Session) -> AdminSession:
    """JWT (Authorization: Bearer … или cookie admin_session) → проверка подписи/срока → строка admin_sessions (отзыв)."""
    token = _bearer_or_cookie_token(request)
    if not token:
        raise HTTPException(401, "Требуется вход администратора")
    claims = decode_token(token)
    if claims is None:
        raise HTTPException(401, "Требуется вход администратора")

    admin_session = db.scalar(
        select(AdminSession)
        .where(
            AdminSession.id == claims["sid"],
            AdminSession.token_hash == hash_session_token(claims["jti"]),
        )
        .join(AdminSession.admin)
    )
    if admin_session is None or str(admin_session.admin_id) != str(claims["sub"]):
        raise HTTPException(401, "Требуется вход администратора")

    request.state.admin_id = admin_session.admin_id  # для журнала действий (middleware)
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


_write_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


async def schedule_write_lock():
    """API-02: проверка конфликтов и commit — одна критическая секция на процесс.
    asyncio.Lock (а не threading): ожидающие запросы не занимают потоки пула, дедлока при N одновременных записей нет.
    ВАЖНО: защищает только в пределах одного процесса — запускать ровно один воркер (SQLite; см. docs/deploy.md)."""
    loop = asyncio.get_running_loop()
    lock = _write_locks.get(loop)
    if lock is None:
        lock = _write_locks[loop] = asyncio.Lock()
    async with lock:
        yield


def _set_session_cookie(response: Response, token: str, refresh_token: str | None = None) -> None:
    """Access-cookie живёт столько же, сколько сессия (просроченный JWT сервер отвергнет → клиент вызовет /refresh);
    refresh-cookie отправляется браузером ТОЛЬКО на /api/admin/refresh и недоступна JS."""
    lifetime = int(settings.session_lifetime().total_seconds())
    response.set_cookie(COOKIE_NAME, token, max_age=lifetime, httponly=True, samesite="lax", secure=settings.cookie_secure(), path="/")
    if refresh_token:
        response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=lifetime, httponly=True, samesite="strict",
                            secure=settings.cookie_secure(), path=REFRESH_PATH)


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure(), httponly=True, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, secure=settings.cookie_secure(), httponly=True, samesite="strict")


def _new_refresh_secret() -> str:
    return generate_session_token()


def _refresh_token(session_id: int, secret: str) -> str:
    return f"{session_id}.{secret}"


def _token_pair(admin: Admin, admin_session: AdminSession, jti: str, now: datetime, refresh_token: str) -> dict:
    access = issue_token(admin_id=admin.id, session_id=admin_session.id, jti=jti, issued_at=now,
                         expires_at=min(now + settings.access_lifetime(), admin_session.expires_at))
    return {
        "admin": admin,
        "access_token": access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(settings.access_lifetime().total_seconds()),
        "refresh_expires_in": int(settings.session_lifetime().total_seconds()),
    }


def _commit_or_raise_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail) from exc

def _raise_if_schedule_conflicts(
    db: Session,
    change: ProposedChange,
) -> None:
    conflicts = ScheduleConflictService(db).check_proposed_state(change)

    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": "Занятие пересекается с существующим расписанием",
                "conflicts": conflicts,
            },
        )

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


def _validate_original_date(session: ClubSession, original_date: date) -> None:
    """API-04: дата отменяемого/переносимого занятия должна выпадать на день недели занятия."""
    if original_date.isoweekday() != session.weekday:
        raise HTTPException(
            422,
            f"original_date {original_date.isoformat()} — это {WEEKDAYS[original_date.isoweekday() - 1]}, "
            f"а занятие проходит по дням: {WEEKDAYS[session.weekday - 1]}",
        )


def _validate_new_date(new_date: date) -> None:
    if new_date.isoweekday() == 7:
        raise HTTPException(422, "Нельзя переносить занятие на воскресенье (в расписании нет воскресных занятий)")
    # Перенос «в прошлое» намеренно НЕ запрещён: админ может задним числом исправлять журнал (решение владельца — PROD_STATUS API-04).


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


@router.post("/login", response_model=LoginResponse)
def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else ""
    login_name = _normalize_login_or_422(payload.login)

    wait = login_limiter.retry_after(db, ip, login_name)
    if wait is not None:
        audit.log("login_blocked", login=login_name, ip=ip, request_id=getattr(request.state, "request_id", None))
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много неудачных попыток входа. Попробуйте через {wait} секунд.",
            headers={"Retry-After": str(wait)},
        )

    admin = db.scalar(select(Admin).where(Admin.login == login_name))
    if admin is None:
        verify_dummy(payload.password)  # SEC-10: одинаковое время ответа
        valid = False
    else:
        valid = verify_password(payload.password, admin.password_hash)

    if not valid:
        login_limiter.record_failure(db, ip, login_name)
        audit.log("login_failed", login=login_name, ip=ip, request_id=getattr(request.state, "request_id", None))
        raise HTTPException(401, "Неверный логин или пароль")

    login_limiter.clear(db, ip, login_name)
    if needs_rehash(admin.password_hash):  # SEC-11: rehash-on-login
        admin.password_hash = hash_password(payload.password, validate=False)
    _purge_expired_sessions(db)  # SEC-12

    jti = generate_session_token()
    secret = _new_refresh_secret()
    now = _utcnow()
    admin_session = AdminSession(
        admin_id=admin.id,
        token_hash=hash_session_token(jti),
        refresh_hash=hash_session_token(secret),
        expires_at=now + settings.session_lifetime(),
    )
    db.add(admin_session)
    _commit_or_raise_conflict(db, "Не удалось создать сессию администратора")
    pair = _token_pair(admin, admin_session, jti, now, _refresh_token(admin_session.id, secret))
    _set_session_cookie(response, pair["access_token"], pair["refresh_token"])
    audit.log("login_ok", login=login_name, ip=ip, admin_id=admin.id, request_id=getattr(request.state, "request_id", None))
    return pair


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    db: Session = Depends(get_db),
):
    """Ротация refresh-токена: каждый вызов выдаёт НОВУЮ пару access+refresh, старый refresh перестаёт работать.
    Повтор уже использованного токена (старше REFRESH_GRACE_SECONDS) = признак кражи → вся сессия отзывается."""
    raw = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE) or ""
    sid_text, _, secret = raw.partition(".")
    unauthorized = HTTPException(401, "Требуется вход администратора")
    if not sid_text.isdigit() or not secret:
        raise unauthorized
    admin_session = db.get(AdminSession, int(sid_text))
    if admin_session is None:
        raise unauthorized
    now = _utcnow()
    presented = hash_session_token(secret)
    ip = request.client.host if request.client else ""
    rid = getattr(request.state, "request_id", None)
    if admin_session.expires_at <= now:
        db.delete(admin_session)
        db.commit()
        raise unauthorized
    if admin_session.refresh_hash != presented:
        if admin_session.refresh_prev_hash and secrets_equal(admin_session.refresh_prev_hash, presented):
            rotated = admin_session.refresh_rotated_at or now
            if (now - rotated).total_seconds() <= settings.refresh_grace_seconds():
                raise HTTPException(409, "Токен только что обновлён другим запросом — повторите с актуальным токеном")
            audit.log("refresh_reuse_detected", admin_id=admin_session.admin_id, session_id=admin_session.id, ip=ip, request_id=rid)
            db.delete(admin_session)
            db.commit()
            _clear_session_cookie(response)
        raise unauthorized
    new_secret = _new_refresh_secret()
    admin_session.refresh_prev_hash = admin_session.refresh_hash
    admin_session.refresh_hash = hash_session_token(new_secret)
    admin_session.refresh_rotated_at = now
    admin_session.expires_at = now + settings.session_lifetime()  # скользящее продление
    jti = generate_session_token()
    admin_session.token_hash = hash_session_token(jti)
    db.commit()
    pair = _token_pair(admin_session.admin, admin_session, jti, now, _refresh_token(admin_session.id, new_secret))
    _set_session_cookie(response, pair["access_token"], pair["refresh_token"])
    audit.log("token_refreshed", admin_id=admin_session.admin_id, ip=ip, request_id=rid)
    return pair


def _purge_expired_sessions(db: Session) -> None:
    db.execute(delete(AdminSession).where(AdminSession.expires_at <= _utcnow()))
    db.commit()


@router.post("/logout", status_code=http_status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    admin_session: AdminSession = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    audit.log("logout", admin_id=admin_session.admin_id)
    db.delete(admin_session)
    db.commit()
    _clear_session_cookie(response)


@router.get("/status", response_model=AdminStatusResponse)
def get_status(current_admin: Admin = Depends(require_admin)):
    return {"admin": current_admin}


@router.post("/password", status_code=http_status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    admin_session: AdminSession = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    """SEC-06: смена пароля; все ОСТАЛЬНЫЕ сессии админа инвалидируются."""
    admin = admin_session.admin
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(403, "Текущий пароль указан неверно")
    try:
        validate_password(payload.new_password, admin.login)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "Новый пароль должен отличаться от текущего")
    admin.password_hash = hash_password(payload.new_password)
    db.execute(
        delete(AdminSession).where(AdminSession.admin_id == admin.id, AdminSession.id != admin_session.id)
    )
    db.commit()
    audit.log("password_changed", admin_id=admin.id)


@router.get(
    "/categories",
    response_model=list[CategoryRead],
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def list_categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name, Category.id)))


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    room = Room(**payload.model_dump())
    db.add(room)
    _commit_or_raise_conflict(db, "Не удалось сохранить аудиторию")
    db.refresh(room)
    return room


@router.patch(
    "/rooms/{room_id}", response_model=RoomRead, dependencies=[Depends(require_admin), Depends(schedule_write_lock)]
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    "/clubs/{club_id}",
    response_model=ClubRead,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def update_club(
    club_id: int,
    payload: ClubUpdate,
    db: Session = Depends(get_db),
):
    club = _get_or_404(db, Club, club_id, "Кружок не найден")
    updates = payload.model_dump(exclude_unset=True)

    if "category_id" in updates:
        _category_exists(db, updates["category_id"])

    if "leader_id" in updates:
        _leader_exists(db, updates["leader_id"])

    final_is_active = updates.get("is_active", club.is_active)
    final_leader_id = updates.get("leader_id", club.leader_id)

    needs_schedule_check = final_is_active and (
        final_leader_id != club.leader_id
        or not club.is_active
    )

    if needs_schedule_check:
        _raise_if_schedule_conflicts(
            db,
            ProposedChange(
                operation="update_club",
                entity_id=club_id,
                payload=updates,
            ),
        )

    _apply_model_updates(club, payload)
    db.commit()
    db.refresh(club)
    return club


@router.delete(
    "/clubs/{club_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    _club_exists(db, payload.club_id)
    _room_exists(db, payload.room_id)

    _raise_if_schedule_conflicts(
        db,
        ProposedChange(
            operation="create_session",
            entity_id=None,
            payload=payload.model_dump(),
        ),
    )

    session = ClubSession(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionRead,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
):
    session = _get_or_404(
        db, ClubSession, session_id, "Регулярное занятие не найдено"
    )
    updates = payload.model_dump(exclude_unset=True)

    if "club_id" in updates:
        _club_exists(db, updates["club_id"])

    if "room_id" in updates:
        _room_exists(db, updates["room_id"])

    has_single_time_boundary = (
        ("start_time" in updates) ^ ("end_time" in updates)
    )

    if has_single_time_boundary:
        updates["start_time"] = updates.get(
            "start_time", session.start_time
        )
        updates["end_time"] = updates.get(
            "end_time", session.end_time
        )
        _validate_interval(
            updates["start_time"],
            updates["end_time"],
            "Начало занятия должно быть раньше конца",
        )

    if "weekday" in updates and updates["weekday"] != session.weekday:
        orphans = db.scalar(
            select(func.count()).select_from(SessionException).where(SessionException.session_id == session.id)
        )
        if orphans:
            raise HTTPException(
                409,
                f"Нельзя менять день недели: у занятия есть отмены/переносы ({orphans}) на прежний день. "
                "Сначала удалите их, затем меняйте день.",
            )

    _raise_if_schedule_conflicts(
        db,
        ProposedChange(
            operation="update_session",
            entity_id=session_id,
            payload=updates,
        ),
    )

    if has_single_time_boundary:
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
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
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def create_cancellation(
    payload: CancellationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    session = _get_or_404(db, ClubSession, payload.session_id, "Регулярное занятие не найдено")
    _validate_original_date(session, payload.original_date)
    exception = SessionException(**_prepare_exception_payload(payload))
    db.add(exception)
    _commit_or_raise_conflict(db, "Не удалось сохранить отмену занятия")
    db.refresh(exception)
    background_tasks.add_task(notify_exception, exception.id)  # push; ошибки глотаются внутри
    return exception


@router.post(
    "/exceptions/moves",
    response_model=SessionExceptionRead,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def create_move(
    payload: MoveCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    session = _get_or_404(db, ClubSession, payload.session_id, "Регулярное занятие не найдено")
    _room_exists(db, payload.new_room_id)
    _validate_original_date(session, payload.original_date)
    _validate_new_date(payload.new_date)

    exception_payload = _prepare_exception_payload(payload)

    _raise_if_schedule_conflicts(
        db,
        ProposedChange(
            operation="create_move",
            entity_id=None,
            payload=exception_payload,
        ),
    )

    exception = SessionException(**exception_payload)
    db.add(exception)
    _commit_or_raise_conflict(db, "Не удалось сохранить перенос занятия")
    db.refresh(exception)
    background_tasks.add_task(notify_exception, exception.id)
    return exception


@router.patch(
    "/exceptions/{exception_id}",
    response_model=SessionExceptionRead,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def update_exception(
    exception_id: int,
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    exception = _get_or_404(
        db, SessionException, exception_id, "Исключение занятия не найдено"
    )
    patch_model = _load_exception_patch(exception, payload)
    updates = _prepare_exception_patch(exception, patch_model)
    user_fields = set(patch_model.model_dump(exclude_unset=True))
    final_session = db.get(ClubSession, updates.get("session_id", exception.session_id))
    if final_session is None:
        raise HTTPException(404, "Регулярное занятие не найдено")
    if user_fields & {"session_id", "original_date"}:
        _validate_original_date(
            final_session, date.fromisoformat(updates.get("original_date", exception.original_date))
        )
    if "new_date" in user_fields and updates.get("new_date"):
        _validate_new_date(date.fromisoformat(updates["new_date"]))
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

    schedule_fields = {
        "session_id",
        "original_date",
        "new_date",
        "new_room_id",
        "new_start_time",
        "new_end_time",
    }

    # API-03: проверка конфликтов и для отмены (раньше — только для переноса)
    if schedule_fields.intersection(user_fields):
        _raise_if_schedule_conflicts(
            db,
            ProposedChange(
                operation="update_move",
                entity_id=exception_id,
                payload=updates,
            ),
        )
    for field, value in updates.items():
        setattr(exception, field, value)
    _commit_or_raise_conflict(db, "Не удалось обновить исключение занятия")
    db.refresh(exception)
    if schedule_fields.intersection(user_fields):  # поменялась дата/время/аудитория — снова уведомляем
        background_tasks.add_task(notify_exception, exception.id)
    return exception


@router.delete(
    "/exceptions/{exception_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin), Depends(schedule_write_lock)],
)
def delete_exception(
    exception_id: int,
    db: Session = Depends(get_db),
):
    exception = _get_or_404(
        db, SessionException, exception_id, "Исключение занятия не найдено"
    )

    _raise_if_schedule_conflicts(
        db,
        ProposedChange(
            operation="delete_exception",
            entity_id=exception_id,
            payload={},
        ),
    )

    db.delete(exception)
    db.commit()
