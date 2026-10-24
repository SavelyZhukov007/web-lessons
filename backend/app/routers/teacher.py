"""Доступ преподавателей (phase 2 F).

Администратор выдаёт руководителю идентификатор `T-…` = 128 случайных бит (не производный от ФИО — иначе его можно подделать).
В БД хранится только SHA-256 токена; показывается он один раз. «Перевыпустить» заменяет хеш, «Отозвать» стирает его —
выданные сессии сразу перестают работать (в сессионном токене зашит момент выдачи доступа).
Преподаватель входит в приложении («Я преподаю»), получает подписанный сессионный токен (12 ч, scope=teacher) и видит
только свои кружки (просмотр), QR занятия, живой список отметившихся с «Удалить», «Отметить по ID». Расписание менять нельзя.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..database import get_db
from ..models.club import Club
from ..models.leader import Leader
from ..models.room import Room
from ..models.session import ClubSession
from . import attendance as att
from .admin import require_admin

router = APIRouter(tags=["teacher"])
SESSION_TTL = 12 * 3600
_B32 = re.compile(r"^[A-Z2-7]{26}$")


def new_access_token() -> str:
    raw = base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")  # 26 символов
    return "T-" + "-".join(raw[i:i + 4] for i in range(0, 26, 4))


def normalize_access_token(raw: str) -> str:
    t = re.sub(r"[\s-]", "", str(raw or "")).upper()
    if t.startswith("T"):
        t = t[1:]
    if not _B32.match(t):
        raise HTTPException(401, "Неверный идентификатор преподавателя")
    return "T-" + "-".join(t[i:i + 4] for i in range(0, 26, 4))


def hash_access(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _skey() -> bytes:
    return hashlib.sha256(b"teacher-session|" + settings.jwt_secret().encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _epoch(dt: datetime | None) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1_000_000) if dt else 0


def make_session(leader: Leader, now: float | None = None) -> str:
    now = int(now if now is not None else time.time())
    body = _b64(json.dumps({"l": leader.id, "a": _epoch(leader.access_issued_at), "e": now + SESSION_TTL, "scope": "teacher"},
                           separators=(",", ":")).encode())
    return f"tch1.{body}.{_b64(hmac.new(_skey(), body.encode(), hashlib.sha256).digest())}"


def _claims(token: str, prefix: str, key: bytes, *, short_signature: bool = False) -> dict:
    """Validate credentials explicitly; interpreter optimization must not change auth."""
    if len(token) > 1000:
        raise ValueError("token too long")
    pre, body, sig = token.split(".")
    good = _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())
    if short_signature:
        good = good[:22]
    if pre != prefix or not hmac.compare_digest(sig, good):
        raise ValueError("invalid signature")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if not isinstance(data, dict) or any(type(data.get(k)) is not int for k in ("l", "a", "e")):
        raise ValueError("invalid claims")
    if data["l"] <= 0 or data["a"] < 0 or data["e"] <= time.time():
        raise ValueError("expired or invalid claims")
    return data


def require_teacher(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Leader:
    tok = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    try:
        data = _claims(tok, "tch1", _skey())
        if data.get("scope") != "teacher":
            raise ValueError("invalid scope")
    except Exception:
        raise HTTPException(401, "Требуется вход преподавателя") from None
    leader = db.get(Leader, data["l"])
    if not leader or not leader.access_hash or _epoch(leader.access_issued_at) != data["a"]:
        raise HTTPException(401, "Доступ преподавателя отозван или перевыпущен")
    return leader


def _own_session(db: Session, leader: Leader, session_id: int) -> ClubSession:
    s = db.get(ClubSession, session_id)
    club = db.get(Club, s.club_id) if s else None
    if not s or not club or club.leader_id != leader.id:
        raise HTTPException(403, "Это занятие не относится к вашим кружкам")
    return s


# ---------- администратор: выдача / перевыпуск / отзыв
class TeacherCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    position: str = Field(default="", max_length=200)


def _issue(db: Session, leader: Leader) -> dict:
    token = new_access_token()
    leader.access_hash = hash_access(token)
    leader.access_issued_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"leader_id": leader.id, "name": leader.name, "token": token, "issued_at": leader.access_issued_at.isoformat() + "Z",
            "note": "Идентификатор показывается один раз — скопируйте и передайте преподавателю."}


@router.post("/api/admin/teachers", status_code=201)
def create_teacher(payload: TeacherCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    leader = Leader(name=" ".join(payload.name.split()), position=payload.position, contact="")
    db.add(leader)
    db.flush()
    return _issue(db, leader)


@router.get("/api/admin/teachers")
def list_teachers(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return [{"leader_id": leader.id, "name": leader.name, "has_access": bool(leader.access_hash),
             "issued_at": leader.access_issued_at.isoformat() + "Z" if leader.access_issued_at else None}
            for leader in db.scalars(select(Leader).order_by(Leader.name))]


@router.post("/api/admin/leaders/{leader_id}/access")
def reissue(leader_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    leader = db.get(Leader, leader_id)
    if not leader:
        raise HTTPException(404, "Руководитель не найден")
    return _issue(db, leader)


@router.delete("/api/admin/leaders/{leader_id}/access", status_code=204)
def revoke(leader_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    leader = db.get(Leader, leader_id)
    if not leader:
        raise HTTPException(404, "Руководитель не найден")
    leader.access_hash = None
    leader.access_issued_at = None
    db.commit()


# ---------- перенос аккаунта преподавателя на новый телефон (t100)
# Админ генерирует одноразовый QR (10 мин). Код подписан и привязан к текущему моменту выдачи доступа (a):
# при погашении доступ перевыпускается → старый телефон и сам код сразу перестают работать (повторно не погасить).
TRANSFER_TTL = 600


def _tkey() -> bytes:
    return hashlib.sha256(b"teacher-transfer|" + settings.jwt_secret().encode()).digest()


def make_transfer(leader: Leader, now: float | None = None) -> str:
    now = int(now if now is not None else time.time())
    body = _b64(json.dumps({"l": leader.id, "a": _epoch(leader.access_issued_at), "e": now + TRANSFER_TTL, "n": secrets.token_hex(4)},
                           separators=(",", ":")).encode())
    return f"itc-tx1.{body}.{_b64(hmac.new(_tkey(), body.encode(), hashlib.sha256).digest())[:22]}"


@router.post("/api/admin/leaders/{leader_id}/transfer")
def create_transfer(leader_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    leader = db.get(Leader, leader_id)
    if not leader:
        raise HTTPException(404, "Руководитель не найден")
    return {"leader_id": leader.id, "name": leader.name, "code": make_transfer(leader), "expires_in": TRANSFER_TTL}


class TransferRedeem(BaseModel):
    code: str = Field(min_length=10, max_length=300)


@router.post("/api/teacher/transfer")
def redeem_transfer(payload: TransferRedeem, db: Session = Depends(get_db)):
    bad = HTTPException(401, "Код переноса недействителен или устарел — попросите администратора показать новый QR")
    try:
        data = _claims(payload.code.strip(), "itc-tx1", _tkey(), short_signature=True)
    except Exception:
        raise bad from None
    leader = db.get(Leader, data["l"])
    if not leader or _epoch(leader.access_issued_at) != data.get("a"):
        raise bad
    issued = _issue(db, leader)  # перевыпуск: прежний телефон отключается, код больше не годится
    return {"access_token": make_session(leader), "token_type": "bearer", "expires_in": SESSION_TTL,
            "teacher": {"id": leader.id, "name": leader.name}, "token": issued["token"]}


# ---------- преподаватель
class TeacherLogin(BaseModel):
    token: str = Field(min_length=10, max_length=80)


@router.post("/api/teacher/login")
def teacher_login(payload: TeacherLogin, db: Session = Depends(get_db)):
    token = normalize_access_token(payload.token)
    leader = db.scalar(select(Leader).where(Leader.access_hash == hash_access(token)))
    if not leader:
        raise HTTPException(401, "Неверный идентификатор преподавателя или доступ отозван")
    return {"access_token": make_session(leader), "token_type": "bearer", "expires_in": SESSION_TTL,
            "teacher": {"id": leader.id, "name": leader.name}}


@router.get("/api/teacher/me")
def teacher_me(leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    clubs = db.scalars(select(Club).where(Club.leader_id == leader.id, Club.is_active.is_(True)).order_by(Club.name)).all()
    ids = [c.id for c in clubs]
    rooms = {r.id: r.name for r in db.scalars(select(Room))}
    sessions = db.scalars(select(ClubSession).where(ClubSession.club_id.in_(ids)).order_by(ClubSession.weekday, ClubSession.start_time)).all() if ids else []
    names = {c.id: c.name for c in clubs}
    return {"id": leader.id, "name": leader.name, "clubs": [{"id": c.id, "name": c.name} for c in clubs],
            "sessions": [{"id": s.id, "club_id": s.club_id, "club_name": names[s.club_id], "weekday": s.weekday,
                          "start_time": s.start_time, "end_time": s.end_time, "room_id": s.room_id, "room_name": rooms.get(s.room_id, "")}
                         for s in sessions]}


@router.post("/api/teacher/attendance/qr")
def teacher_qr(payload: att.SessionDay, leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    _own_session(db, leader, payload.session_id)
    return att._qr_payload(db, payload.session_id, payload.date, payload.original_date)


@router.get("/api/teacher/occurrences")
def teacher_occurrences(date: str = Query(), days: int = Query(1, ge=1, le=14), leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    return att._day_events(db, date, days, leader.id)


@router.get("/api/teacher/attendance")
def teacher_list(session_id: int = Query(gt=0), date: str = Query(), since_id: int = Query(0, ge=0), original_date: str | None = Query(None),
                 leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    """Живой список (опрос раз в 2 с; since_id — только новые)."""
    _own_session(db, leader, session_id)
    return att._list(db, session_id, date, since_id, original_date)


@router.delete("/api/teacher/attendance/{att_id}", status_code=204)
def teacher_delete(att_id: int, leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    own = set(db.scalars(select(ClubSession.id).join(Club, Club.id == ClubSession.club_id).where(Club.leader_id == leader.id)))
    att._delete(db, att_id, f"teacher:{leader.id}", own)


@router.post("/api/teacher/attendance/manual", status_code=201)
def teacher_manual(payload: att.ManualMark, leader: Leader = Depends(require_teacher), db: Session = Depends(get_db)):
    _own_session(db, leader, payload.session_id)
    return att._record(db, payload.session_id, payload.date, payload.student_id, "manual", enforce="session", original_date=payload.original_date)
