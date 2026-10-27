from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import re
import weakref
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone

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
from sqlalchemy import delete, func, or_, select
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
from ..models.assignments import ClubLeader, SessionLeader, SessionRoom
from ..models.category import Category
from ..models.club import Club
from ..models.import_draft import ImportDraft
from ..models.leader import Leader
from ..models.period import AcademicPeriod, NoClassDay
from ..models.room import Room
from ..models.session import ClubSession
from ..models.session_exception import SessionException
from ..schemas.admin import AdminLoginRequest, AdminStatusResponse, LoginResponse, PasswordChangeRequest, RefreshRequest
from ..schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from ..schemas.club import ClubCreate, ClubRead, ClubUpdate
from ..schemas.import_draft import ImportDecisions, ImportUpload
from ..schemas.leader import LeaderCreate, LeaderRead, LeaderUpdate
from ..schemas.period import NoClassInput, NoClassRange, NoClassRead, PeriodInput, PeriodRead
from ..schemas.room import RoomCreate, RoomRead, RoomUpdate
from ..schemas.session import SessionCreate, SessionRead, SessionUpdate
from ..schemas.session_exception import (
    CancellationCreate,
    CancellationUpdate,
    MoveCreate,
    MoveUpdate,
    SessionExceptionRead,
)
from ..services import audit, login_limiter, occurrence_source
from ..services import conflicts as conflict_engine
from ..services.importer.parser import read_rows
from ..services.occurrences import original_occurs
from ..services.push import notify_exception
from ..services.schedule_conflicts import ProposedChange
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
_confirmed_conflicts: ContextVar[frozenset[str]] = ContextVar("confirmed_conflicts", default=frozenset())


async def schedule_write_lock(request: Request):
    """API-02: проверка конфликтов и commit — одна критическая секция на процесс.
    asyncio.Lock (а не threading): ожидающие запросы не занимают потоки пула, дедлока при N одновременных записей нет.
    ВАЖНО: защищает только в пределах одного процесса — запускать ровно один воркер (SQLite; см. docs/deploy.md)."""
    loop = asyncio.get_running_loop()
    lock = _write_locks.get(loop)
    if lock is None:
        lock = _write_locks[loop] = asyncio.Lock()
    async with lock:
        confirmations = frozenset(request.headers.get("X-Confirmed-Conflicts", "").split(","))
        token = _confirmed_conflicts.set(confirmations)
        try:
            yield
        finally:
            _confirmed_conflicts.reset(token)


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
    """Конфликты по реальным датам occurrence (services.conflicts, schedule v2)."""
    snapshot = occurrence_source.load_snapshot(db)
    found = conflict_engine.check_change(
        db, change.operation, change.entity_id, change.payload, snapshot=snapshot
    )
    if not found:
        return
    # Confirmation applies only to the exact proposed change and conflict set.
    # A subsequent request always recalculates both under schedule_write_lock.
    fingerprint = hashlib.sha256(json.dumps({
        "operation": change.operation, "entity_id": change.entity_id,
        "payload": change.payload,
        "conflicts": sorted(str(c.key) for c in found),
    }, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    if fingerprint in _confirmed_conflicts.get():
        audit.log("schedule_conflicts_confirmed", operation=change.operation,
                  entity_id=change.entity_id, conflicts=len(found))
        return
    after, touched = conflict_engine.apply_change(
        snapshot, change.operation, change.entity_id, change.payload
    )
    conflicts = conflict_engine.merge_described(
        [conflict_engine.describe(after, c, touched=touched) for c in found]
    )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "CONFLICT",
            "message": "Занятие пересекается с существующим расписанием",
            "conflicts": conflicts,
            "confirmation_token": fingerprint,
        },
    )


def _confirm_calendar_conflicts(operation: str, payload: dict, conflicts: list[dict]) -> None:
    if not conflicts:
        return
    fingerprint = hashlib.sha256(json.dumps({"operation": operation, "payload": payload,
        "conflicts": conflicts}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    if fingerprint in _confirmed_conflicts.get():
        audit.log("schedule_conflicts_confirmed", operation=operation, conflicts=len(conflicts))
        return
    raise HTTPException(409, detail={"code": "CONFLICT", "message": "Изменение создаёт пересечения в расписании",
        "conflicts": conflicts, "confirmation_token": fingerprint})


def _calendar_overlap_details(event: dict, events: list[dict]) -> list[dict]:
    from ..services.conflicts import find_conflicts
    by_id = {item["event_id"]: item for item in events}
    result = []
    for conflict in find_conflicts(event, events, exclude_event_id=event["event_id"]):
        other = by_id[conflict["event_id"]]
        result.append({"event_id": other["event_id"], "club_name": other.get("club_name", ""),
            "date": other["date"], "start_time": other["start_time"], "end_time": other["end_time"],
            "room_name": other.get("room_name", ""), "leader_name": other.get("leader_name", ""),
            "reasons": conflict["reasons"], "changed_event_id": event["event_id"]})
    return result


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


def _validate_original_date(db: Session, session: ClubSession, original_date: date) -> None:
    """API-04: дата отменяемого/переносимого занятия должна выпадать на день недели занятия."""
    if session.one_off_date and original_date.isoformat() != session.one_off_date:
        raise HTTPException(422, f"Разовое занятие назначено только на {session.one_off_date}")
    if original_date.isoweekday() != session.weekday:
        raise HTTPException(
            422,
            f"original_date {original_date.isoformat()} — это {WEEKDAYS[original_date.isoweekday() - 1]}, "
            f"а занятие проходит по дням: {WEEKDAYS[session.weekday - 1]}",
        )
    if session.period_id:
        period = db.get(AcademicPeriod, session.period_id)
        days = set(db.scalars(select(NoClassDay.date).where(NoClassDay.period_id == session.period_id)))
        info = {"start_date": period.start_date, "end_date": period.end_date, "even_week_start": period.even_week_start}
        if not original_occurs({"weekday": session.weekday, "one_off_date": session.one_off_date, "repeat": session.repeat}, original_date, info, days):
            raise HTTPException(409, "На эту дату занятие не запланировано с учётом периода, повторения и каникул")


def _reject_existing_exception(db: Session, session_id: int, original_date: date, exclude_id: int | None = None) -> None:
    query = select(SessionException).where(
        SessionException.session_id == session_id,
        SessionException.original_date == original_date.isoformat(),
    )
    if exclude_id is not None:
        query = query.where(SessionException.id != exclude_id)
    existing = db.scalar(query)
    if existing:
        state = "уже отменено" if existing.type == "cancelled" else "уже перенесено"
        raise HTTPException(409, f"Занятие на {original_date.strftime('%d.%m.%Y')} {state}. Откройте раздел «Изменения», чтобы изменить существующую запись.")


def _validate_new_date(new_date: date) -> None:
    if new_date.isoweekday() == 7:
        raise HTTPException(422, "Нельзя переносить занятие на воскресенье (в расписании нет воскресных занятий)")
    # Перенос «в прошлое» намеренно НЕ запрещён: админ может задним числом исправлять журнал (решение владельца — PROD_STATUS API-04).


def _validate_target_date(db: Session, session: ClubSession, new_date: date) -> None:
    if not session.period_id:
        return
    period = db.get(AcademicPeriod, session.period_id)
    day = new_date.isoformat()
    if not period.start_date <= day <= period.end_date:
        raise HTTPException(409, "Нельзя перенести занятие за границы учебного периода")
    if db.scalar(select(NoClassDay.id).where(NoClassDay.period_id == session.period_id, NoClassDay.date == day)):
        raise HTTPException(409, "Нельзя перенести занятие на неучебный день")


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
    if has_clubs is not None or db.scalar(select(ClubLeader.club_id).where(ClubLeader.leader_id == leader_id).limit(1)) is not None or db.scalar(select(SessionLeader.session_id).where(SessionLeader.leader_id == leader_id).limit(1)) is not None:
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
    _check_room_unique(db, payload.name, payload.building)
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
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates or "building" in updates:
        _check_room_unique(db, updates.get("name", room.name), updates.get("building", room.building), room_id)
    if payload.is_remote is not None and payload.is_remote != room.is_remote and (db.scalar(select(ClubSession.id).where(ClubSession.room_id == room_id).limit(1)) is not None or db.scalar(select(SessionRoom.session_id).where(SessionRoom.room_id == room_id).limit(1)) is not None or db.scalar(select(SessionException.id).where(SessionException.new_room_id == room_id).limit(1)) is not None):
        raise HTTPException(409, "Нельзя менять формат используемой аудитории")
    _apply_model_updates(room, payload)
    _commit_or_raise_conflict(db, "Не удалось обновить аудиторию")
    db.refresh(room)
    return room


def _check_room_unique(db: Session, name: str, building: str | None, exclude_id: int | None = None):
    same_building = Room.building == building if building else or_(Room.building.is_(None), Room.building == "")
    statement = select(Room.id).where(Room.name == name, same_building)
    if exclude_id is not None:
        statement = statement.where(Room.id != exclude_id)
    if db.scalar(statement.limit(1)) is not None:
        raise HTTPException(409, "Аудитория с таким названием и корпусом уже существует")


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
    if has_sessions is not None or db.scalar(select(SessionRoom.session_id).where(SessionRoom.room_id == room_id).limit(1)) is not None:
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
    values = payload.model_dump()
    leader_ids = set(values.pop("leader_ids")) | {payload.leader_id}
    for leader_id in leader_ids:
        _leader_exists(db, leader_id)
    club = Club(**values)
    club.leaders = [db.get(Leader, leader_id) for leader_id in sorted(leader_ids)]
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
    if "leader_ids" in updates:
        for leader_id in updates["leader_ids"]:
            _leader_exists(db, leader_id)

    final_is_active = updates.get("is_active", club.is_active)
    final_leader_id = updates.get("leader_id", club.leader_id)
    if "leader_id" in updates and "leader_ids" not in updates and final_leader_id != club.leader_id:
        updates["leader_ids"] = sorted((set(club.leader_ids) - {club.leader_id}) | {final_leader_id})

    needs_schedule_check = final_is_active and (
        final_leader_id != club.leader_id
        or not club.is_active
        or "leader_ids" in updates
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

    leader_ids = updates.pop("leader_ids", None)
    if leader_ids is not None:
        club.leaders = [db.get(Leader, leader_id) for leader_id in sorted(set(leader_ids) | {final_leader_id})]
    elif final_leader_id != club.leader_id:
        club.leaders = [db.get(Leader, leader_id) for leader_id in sorted((set(club.leader_ids) - {club.leader_id}) | {final_leader_id})]
    for field, value in updates.items():
        setattr(club, field, value)
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
    if payload.period_id and not db.get(AcademicPeriod, payload.period_id):
        raise HTTPException(404, "Учебный период не найден")
    if payload.period_id and payload.one_off_date:
        period = db.get(AcademicPeriod, payload.period_id)
        days = set(db.scalars(select(NoClassDay.date).where(NoClassDay.period_id == payload.period_id)))
        if not original_occurs(payload.model_dump(mode="json"), payload.one_off_date, {"start_date": period.start_date, "end_date": period.end_date, "even_week_start": period.even_week_start}, days):
            raise HTTPException(409, "Разовое занятие попадает за пределы периода или на неучебный день")

    values = payload.model_dump(mode="json")
    leader_ids = sorted(set(values.pop("leader_ids")))
    room_ids = [payload.room_id, *sorted(set(values.pop("room_ids")) - {payload.room_id})]
    for leader_id in leader_ids:
        _leader_exists(db, leader_id)
    for room_id in room_ids:
        _room_exists(db, room_id)
    _raise_if_schedule_conflicts(
        db,
        ProposedChange(
            operation="create_session",
            entity_id=None,
            payload={**values, "leader_ids": leader_ids, "room_ids": room_ids},
        ),
    )

    session = ClubSession(**values)
    session.leaders = [db.get(Leader, leader_id) for leader_id in leader_ids]
    session.rooms = [db.get(Room, room_id) for room_id in room_ids]
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
    updates = payload.model_dump(exclude_unset=True, mode="json")
    for leader_id in updates.get("leader_ids", []):
        _leader_exists(db, leader_id)
    for room_id in updates.get("room_ids", []):
        _room_exists(db, room_id)
    if "room_ids" in updates:
        primary_room = updates.get("room_id", session.room_id)
        updates["room_ids"] = [primary_room, *sorted(set(updates["room_ids"]) - {primary_room})]
    elif "room_id" in updates and updates["room_id"] != session.room_id:
        updates["room_ids"] = [updates["room_id"], *sorted(set(session.room_ids) - {session.room_id, updates["room_id"]})]

    final_date = updates.get("one_off_date", session.one_off_date)
    final_weekday = updates.get("weekday", session.weekday)
    final_period = updates.get("period_id", session.period_id)
    final_repeat = updates.get("repeat", session.repeat)
    if final_period and not db.get(AcademicPeriod, final_period):
        raise HTTPException(404, "Учебный период не найден")
    if final_repeat in ("even", "odd") and not final_period:
        raise HTTPException(422, "Для чётных и нечётных недель необходим учебный период")
    if (final_repeat == "once") != bool(final_date):
        raise HTTPException(422, "Разовое занятие должно иметь дату")
    if final_period and final_date:
        period = db.get(AcademicPeriod, final_period)
        days = set(db.scalars(select(NoClassDay.date).where(NoClassDay.period_id == final_period)))
        if not original_occurs({"weekday": final_weekday, "one_off_date": final_date, "repeat": final_repeat}, date.fromisoformat(final_date), {"start_date": period.start_date, "end_date": period.end_date, "even_week_start": period.even_week_start}, days):
            raise HTTPException(409, "Разовое занятие попадает за пределы периода или на неучебный день")
    pattern_changed = ("repeat" in updates and updates["repeat"] != session.repeat) or ("period_id" in updates and updates["period_id"] != session.period_id)
    if pattern_changed and db.scalar(select(func.count()).select_from(SessionException).where(SessionException.session_id == session.id)):
        raise HTTPException(409, "Сначала удалите отмены и переносы этого занятия")
    if final_date and date.fromisoformat(final_date).isoweekday() != final_weekday:
        raise HTTPException(422, "День недели должен совпадать с датой разового занятия")
    if "one_off_date" in updates and updates["one_off_date"] != session.one_off_date:
        if db.scalar(select(func.count()).select_from(SessionException).where(SessionException.session_id == session.id)):
            raise HTTPException(409, "Сначала удалите отмены и переносы этого занятия, затем измените дату")

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

    leader_ids = updates.pop("leader_ids", None)
    room_ids = updates.pop("room_ids", None)
    if leader_ids is not None:
        session.leaders = [db.get(Leader, leader_id) for leader_id in sorted(set(leader_ids))]
    if room_ids is not None:
        session.rooms = [db.get(Room, room_id) for room_id in room_ids]
    for field, value in updates.items():
        setattr(session, field, value)

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
    _validate_original_date(db, session, payload.original_date)
    _reject_existing_exception(db, payload.session_id, payload.original_date)
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
    _validate_original_date(db, session, payload.original_date)
    _reject_existing_exception(db, payload.session_id, payload.original_date)
    _validate_new_date(payload.new_date)
    _validate_target_date(db, session, payload.new_date)

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
            db, final_session, date.fromisoformat(updates.get("original_date", exception.original_date))
        )
        _reject_existing_exception(db, final_session.id, date.fromisoformat(updates.get("original_date", exception.original_date)), exception.id)
    if "new_date" in user_fields and updates.get("new_date"):
        _validate_new_date(date.fromisoformat(updates["new_date"]))
    if exception.type == "moved":
        _validate_target_date(db, final_session, date.fromisoformat(updates.get("new_date", exception.new_date)))
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


@router.get("/periods", response_model=list[PeriodRead], dependencies=[Depends(require_admin)])
def list_periods(db: Session = Depends(get_db)):
    return list(db.scalars(select(AcademicPeriod).order_by(AcademicPeriod.start_date)))


@router.post("/periods", response_model=PeriodRead, status_code=201, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def create_period(payload: PeriodInput, db: Session = Depends(get_db)):
    period = AcademicPeriod(**payload.model_dump(mode="json"))
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.put("/periods/{period_id}", response_model=PeriodRead, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def update_period(period_id: int, payload: PeriodInput, db: Session = Depends(get_db)):
    period = _get_or_404(db, AcademicPeriod, period_id, "Учебный период не найден")
    from ..services.schedule import build_week
    from .public import _dump_schedule_data

    proposed = payload.model_dump(mode="json")
    data = _dump_schedule_data(db)
    holidays = {d["date"] for d in data["no_class_days"] if d["period_id"] == period_id}
    if any(not proposed["start_date"] <= day <= proposed["end_date"] for day in holidays):
        raise HTTPException(409, "Неучебные дни не должны выходить за границы периода")
    sessions = {s["id"]: s for s in data["sessions"] if s.get("period_id") == period_id}
    for exception in data["session_exceptions"]:
        if exception["session_id"] in sessions and not original_occurs(sessions[exception["session_id"]], date.fromisoformat(exception["original_date"]), proposed, holidays):
            raise HTTPException(409, "Изменение периода сделает существующую отмену или перенос недействительным")
        if exception["session_id"] in sessions and exception["type"] == "moved" and (not proposed["start_date"] <= exception["new_date"] <= proposed["end_date"] or exception["new_date"] in holidays):
            raise HTTPException(409, "Изменение периода сделает дату переноса недействительной")
    for current in data["periods"]:
        if current["id"] == period_id:
            current.update(proposed)
    start, end = date.fromisoformat(proposed["start_date"]), date.fromisoformat(proposed["end_date"])
    week = start - timedelta(days=start.weekday())
    conflicts = []
    while week <= end:
        events = build_week(week, data)
        for event in events:
            if event["session_id"] in sessions and event["status"] != "cancelled":
                conflicts.extend(_calendar_overlap_details(event, events))
        week += timedelta(days=7)
    _confirm_calendar_conflicts("update_period", {"id": period_id, **proposed}, conflicts)
    for key, value in proposed.items():
        setattr(period, key, value)
    db.commit()
    return period


@router.delete("/periods/{period_id}", status_code=204, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def delete_period(period_id: int, db: Session = Depends(get_db)):
    period = _get_or_404(db, AcademicPeriod, period_id, "Учебный период не найден")
    if db.scalar(select(func.count()).select_from(ClubSession).where(ClubSession.period_id == period_id)):
        raise HTTPException(409, "Период используется занятиями")
    db.delete(period)
    db.commit()


@router.get("/periods/{period_id}/days-off", response_model=list[NoClassRead], dependencies=[Depends(require_admin)])
def list_days_off(period_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, AcademicPeriod, period_id, "Учебный период не найден")
    return list(db.scalars(select(NoClassDay).where(NoClassDay.period_id == period_id).order_by(NoClassDay.date)))


@router.post("/periods/{period_id}/days-off", response_model=NoClassRead, status_code=201, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def add_day_off(period_id: int, payload: NoClassInput, db: Session = Depends(get_db)):
    period = _get_or_404(db, AcademicPeriod, period_id, "Учебный период не найден")
    day = payload.date.isoformat()
    if not period.start_date <= day <= period.end_date:
        raise HTTPException(422, "Дата вне учебного периода")
    # Существующие исключения нельзя сделать невидимыми изменением календаря.
    existing = db.scalar(select(func.count()).select_from(SessionException).join(ClubSession).where(ClubSession.period_id == period_id, or_(SessionException.original_date == day, SessionException.new_date == day)))
    if existing:
        raise HTTPException(409, "На эту дату уже есть отмены или переносы занятий")
    if db.scalar(select(NoClassDay.id).where(NoClassDay.period_id == period_id, NoClassDay.date == day)):
        raise HTTPException(409, "Этот день уже отмечен как неучебный")
    item = NoClassDay(period_id=period_id, date=day, reason=payload.reason)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/periods/{period_id}/days-off/range", status_code=201, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def add_days_off(period_id: int, payload: NoClassRange, db: Session = Depends(get_db)):
    period = _get_or_404(db, AcademicPeriod, period_id, "Учебный период не найден")
    start, end = payload.start_date.isoformat(), payload.end_date.isoformat()
    if not period.start_date <= start <= end <= period.end_date:
        raise HTTPException(422, "Даты выходят за границы учебного периода")
    existing = db.scalar(select(func.count()).select_from(SessionException).join(ClubSession).where(ClubSession.period_id == period_id, or_(SessionException.original_date.between(start, end), SessionException.new_date.between(start, end))))
    if existing:
        raise HTTPException(409, "В этот период уже есть отмены или переносы занятий")
    known = set(db.scalars(select(NoClassDay.date).where(NoClassDay.period_id == period_id, NoClassDay.date.between(start, end))))
    day = payload.start_date
    added = 0
    while day <= payload.end_date:
        if day.isoformat() not in known:
            db.add(NoClassDay(period_id=period_id, date=day.isoformat(), reason=payload.reason))
            added += 1
        day += timedelta(days=1)
    db.commit()
    return {"added": added}


@router.delete("/periods/{period_id}/days-off/{day_id}", status_code=204, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def delete_day_off(period_id: int, day_id: int, db: Session = Depends(get_db)):
    item = _get_or_404(db, NoClassDay, day_id, "День не найден")
    if item.period_id != period_id:
        raise HTTPException(404, "День не найден")
    from ..services.schedule import build_week
    from .public import _dump_schedule_data

    # При возвращении занятий проверяем все их ресурсы на исходную дату.
    data = _dump_schedule_data(db)
    data["no_class_days"] = [d for d in data["no_class_days"] if not (d["period_id"] == period_id and d["date"] == item.date)]
    day = date.fromisoformat(item.date)
    events = build_week(day - timedelta(days=day.weekday()), data)
    period_sessions = {s["id"] for s in data["sessions"] if s.get("period_id") == period_id}
    conflicts = []
    for event in events:
        if event["session_id"] in period_sessions and event["date"] == item.date and event["status"] != "cancelled":
            conflicts.extend(_calendar_overlap_details(event, events))
    _confirm_calendar_conflicts("restore_day", {"period_id": period_id, "day_id": day_id, "date": item.date}, conflicts)
    db.delete(item)
    db.commit()


def _draft_data(item: ImportDraft) -> dict:
    return {"id": item.id, "filename": item.filename, "status": item.status,
            "rows": json.loads(item.rows_json), "decisions": json.loads(item.decisions_json)}


@router.get("/imports", dependencies=[Depends(require_admin)])
def list_imports(db: Session = Depends(get_db)):
    return [_draft_data(item) for item in db.scalars(select(ImportDraft).order_by(ImportDraft.id.desc()).limit(50))]


@router.post("/imports", status_code=201, dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def create_import(payload: ImportUpload, db: Session = Depends(get_db)):
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
        rows = read_rows(payload.filename, content)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, str(exc)) from exc
    existing_clubs = list(db.scalars(select(Club)))
    existing_leaders = list(db.scalars(select(Leader)))
    existing_rooms = list(db.scalars(select(Room)))
    for row in rows:
        matches = [club.id for club in existing_clubs if club.name.casefold() == row["club_name"].casefold()]
        row["matching_club_ids"] = matches
        leader_names = {part.strip().casefold() for part in row["leaders"].split("/")}
        row["matching_leader_ids"] = [leader.id for leader in existing_leaders if leader.name.strip().casefold() in leader_names]
        room_names = {re.sub(r"\s*каб\.?\s*$", "", part, flags=re.I).strip().casefold() for part in row["rooms"].split("/")}
        row["matching_room_ids"] = [room.id for room in existing_rooms if room.name.strip().casefold() in room_names]
        if matches:
            row["issues"].append("Есть кружок с таким названием — проверьте, совпадает ли он")
        if row["matching_leader_ids"]:
            row["issues"].append("Найдены возможные совпадения руководителей")
        if row["matching_room_ids"]:
            row["issues"].append("Найдены возможные совпадения аудиторий; проверьте корпус")
    filename = payload.filename.replace("\\", "/").rsplit("/", 1)[-1]
    item = ImportDraft(filename=filename, rows_json=json.dumps(rows, ensure_ascii=False), decisions_json="[]", status="draft")
    db.add(item)
    db.commit()
    db.refresh(item)
    return _draft_data(item)


@router.put("/imports/{draft_id}/decisions", dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def update_import_decisions(draft_id: int, payload: ImportDecisions, db: Session = Depends(get_db)):
    item = _get_or_404(db, ImportDraft, draft_id, "Черновик не найден")
    if item.status != "draft":
        raise HTTPException(409, "Этот черновик уже опубликован")
    valid_rows = {row["row"] for row in json.loads(item.rows_json)}
    numbers = [decision.row for decision in payload.decisions]
    if len(numbers) != len(set(numbers)) or not set(numbers) <= valid_rows:
        raise HTTPException(422, "Проверьте номера строк и повторяющиеся решения")
    item.decisions_json = json.dumps([d.model_dump(mode="json") for d in payload.decisions], ensure_ascii=False)
    db.commit()
    return _draft_data(item)


@router.post("/imports/{draft_id}/publish", dependencies=[Depends(require_admin), Depends(schedule_write_lock)])
def publish_import(draft_id: int, db: Session = Depends(get_db)):
    item = _get_or_404(db, ImportDraft, draft_id, "Черновик не найден")
    if item.status != "draft":
        raise HTTPException(409, "Этот черновик уже опубликован")
    rows = {r["row"]: r for r in json.loads(item.rows_json)}
    decisions = json.loads(item.decisions_json)
    if {d["row"] for d in decisions} != set(rows):
        raise HTTPException(409, "Для каждой строки выберите создание или пропуск")
    from ..services import import_publish as import_journal

    backup_path = import_journal.backup_before_draft()  # schedule v2: снимок для отката публикации
    created = 0
    new_clubs = {}
    for decision in decisions:
        if decision["action"] == "skip":
            continue
        row = dict(rows[decision["row"]])
        for field in ("weekday", "start_time", "end_time", "club_name"):
            if decision.get(field) is not None:
                row[field] = decision[field]
        if not row["weekday"] or not row["start_time"] or not row["end_time"] or not decision["room_ids"]:
            raise HTTPException(422, f"Строка {row['row']}: проверьте день, время и аудиторию")
        for room_id in decision["room_ids"]:
            _room_exists(db, room_id)
        for leader_id in decision["leader_ids"]:
            _leader_exists(db, leader_id)
        if decision["period_id"] and not db.get(AcademicPeriod, decision["period_id"]):
            raise HTTPException(404, f"Строка {row['row']}: период не найден")
        if decision["club_id"]:
            club = _get_or_404(db, Club, decision["club_id"], f"Строка {row['row']}: кружок не найден")
        else:
            if not decision["category_id"] or not decision["leader_id"]:
                raise HTTPException(422, f"Строка {row['row']}: укажите направление и основного руководителя")
            _category_exists(db, decision["category_id"])
            _leader_exists(db, decision["leader_id"])
            key = (row["club_name"].casefold(), decision["category_id"], decision["leader_id"])
            club = new_clubs.get(key)
            if club is None:
                club = Club(name=row["club_name"], description="", category_id=decision["category_id"], leader_id=decision["leader_id"], is_active=True)
                club.leaders = [db.get(Leader, x) for x in sorted(set(decision["leader_ids"]) | {decision["leader_id"]})]
                db.add(club)
                db.flush()
                new_clubs[key] = club
        values = {"club_id": club.id, "room_id": decision["room_ids"][0], "weekday": row["weekday"], "start_time": row["start_time"], "end_time": row["end_time"], "period_id": decision["period_id"], "repeat": decision["repeat"], "leader_ids": decision["leader_ids"], "room_ids": decision["room_ids"]}
        try:
            validated = SessionCreate.model_validate(values).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(422, f"Строка {row['row']}: {exc}") from exc
        try:
            _raise_if_schedule_conflicts(db, ProposedChange(operation="create_session", entity_id=None, payload=validated))
        except HTTPException as exc:
            if isinstance(exc.detail, dict):
                detail = {**exc.detail, "message": f"Строка {row['row']}: {exc.detail.get('message', 'конфликт расписания')}"}
                raise HTTPException(exc.status_code, detail) from exc
            raise HTTPException(exc.status_code, f"Строка {row['row']}: {exc.detail}") from exc
        leader_ids = validated.pop("leader_ids")
        room_ids = validated.pop("room_ids")
        session = ClubSession(**validated)
        session.leaders = [db.get(Leader, x) for x in sorted(set(leader_ids))]
        session.rooms = [db.get(Room, x) for x in sorted(set(room_ids))]
        db.add(session)
        db.flush()
        created += 1
    item.status = "published"
    db.commit()
    entry = import_journal.record_draft_publish(item.id, backup_path, created=created, skipped=len(decisions) - created)
    return {"id": item.id, "status": item.status, "created": created, "skipped": len(decisions) - created, "publish_id": entry.get("id")}
