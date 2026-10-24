"""Посещаемость (phase 2 F, анонимная).

Преподаватель (или администратор) открывает занятие → полноэкранный QR, который обновляется каждые ~25 с и действует 60 с:
`itc-att2.<body>.<sig>`, body = {s: session_id, d: дата занятия, i: выдан, e: истекает}, подпись HMAC-SHA256 (ключ — производный
от JWT-секрета). Студент сканирует QR в приложении и отправляет {student_id, session_id, qr_token, nonce}. Сервер проверяет
подпись, срок, совпадение занятия (QR одного занятия нельзя использовать для другого), одноразовость nonce и «одна отметка
на студента на занятие». Имён студентов сервер не получает: только ID `S-…` (HMAC от ФИО|группы на секрете устройства — по
имени его не вычислить). Отметки хранятся 21 день и удаляются автоматически (purge при старте и при обращениях).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import settings
from ..database import get_db
from ..models.attendance import Attendance, QrNonce, StudentDevice
from ..models.club import Club
from ..models.leader import Leader
from ..models.session import ClubSession
from ..models.session_exception import SessionException
from ..services.clock import MSK, now_msk
from ..services import audit
from .admin import require_admin


def window_minutes() -> int:
    """Сколько минут от начала занятия открыта отметка по QR (ATTENDANCE_WINDOW_MIN, по умолчанию 15)."""
    import os
    try:
        return max(1, min(240, int(os.getenv("ATTENDANCE_WINDOW_MIN", "15"))))
    except ValueError:
        return 15


def _now_ts() -> float:
    return now_msk().timestamp()

router = APIRouter(tags=["attendance"])
PREFIX = "itc-att2."
QR_TTL = 60          # секунд действует один QR
QR_EARLY = 10        # QR открывается за 10 с до начала занятия
QR_ROTATE = 25       # клиент запрашивает новый QR каждые 25 с
RETENTION_DAYS = 21
STUDENT_RE = re.compile(r"^S-[A-Z2-7]{4}(?:-[A-Z2-7]{4}){5}-[A-Z2-7]{2}$")


def normalize_student_id(raw: str) -> str:
    """'s-abcd efgh…' / без дефисов → 'S-ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ' (26 символов base32 = 130 бит ≥ 128)."""
    t = re.sub(r"[\s-]", "", str(raw or "")).upper()
    if t.startswith("S"):
        t = t[1:]
    if len(t) != 26 or not re.fullmatch(r"[A-Z2-7]{26}", t):
        raise ValueError("ID студента выглядит так: S-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX")
    return "S-" + "-".join(t[i:i + 4] for i in range(0, 26, 4))


def short_id(sid: str) -> str:
    return sid[:7] + "…" + sid[-2:]


def _key() -> bytes:
    return hashlib.sha256(b"attendance-qr2|" + settings.jwt_secret().encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(session_id: int, day: str, now: float | None = None) -> tuple[str, int]:
    now = int(now if now is not None else _now_ts())
    body = _b64(json.dumps({"s": session_id, "d": day, "i": now, "e": now + QR_TTL}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest()[:16])
    return f"{PREFIX}{body}.{sig}", now + QR_TTL


def read_token(token: str, now: float | None = None) -> dict:
    try:
        if not token.startswith(PREFIX):
            raise ValueError
        body, sig = token[len(PREFIX):].split(".")
        good = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest()[:16])
        if not hmac.compare_digest(sig, good):
            raise ValueError
        data = json.loads(_unb64(body))
        int(data["s"]); date.fromisoformat(data["d"]); int(data["e"])
    except Exception:
        raise HTTPException(400, "QR-код не распознан: это не код посещаемости ИТК") from None
    if data["e"] < (now if now is not None else _now_ts()):
        raise HTTPException(410, "QR-код устарел — отсканируйте код на экране преподавателя ещё раз")
    return data


def purge(db: Session) -> int:
    """Удалить отметки старше 21 дня и истёкшие nonce. Вызывается при старте и при обращениях."""
    cutoff = (now_msk().date() - timedelta(days=RETENTION_DAYS)).isoformat()
    n = db.execute(delete(Attendance).where(Attendance.occurrence_date < cutoff)).rowcount or 0
    db.execute(delete(QrNonce).where(QrNonce.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)))
    db.commit()
    return n


def _occurrence(db: Session, session_id: int, day: str):
    """Занятие в этот день: (session, club, start, end) с учётом переноса; 404/409 если его нет или оно отменено."""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, "date должен иметь формат YYYY-MM-DD") from None
    s = db.get(ClubSession, session_id)
    if not s:
        raise HTTPException(404, "Занятие не найдено")
    club = db.get(Club, s.club_id)
    exc = db.scalar(select(SessionException).where(SessionException.session_id == s.id, SessionException.original_date == day))
    if exc and exc.type == "cancelled":
        raise HTTPException(409, "Это занятие отменено")
    if exc is None and d.isoweekday() != s.weekday:
        # может быть днём, на который перенесли занятие
        moved = db.scalar(select(SessionException).where(SessionException.session_id == s.id, SessionException.new_date == day))
        if not moved:
            raise HTTPException(404, "В этот день у кружка нет занятия")
        return s, club, moved.new_start_time, moved.new_end_time, moved.original_date
    if exc and exc.type == "moved":
        return s, club, exc.new_start_time, exc.new_end_time, day
    return s, club, s.start_time, s.end_time, day




def _times(day: str, start: str, end: str) -> tuple[float, float]:
    d = date.fromisoformat(day)
    mk = lambda hm: datetime(d.year, d.month, d.day, int(hm[:2]), int(hm[3:5]), tzinfo=MSK).timestamp()  # noqa: E731
    return mk(start), mk(end)


def _record(db: Session, session_id: int, day: str, student_id: str, method: str, *, enforce: str | None = None,
            at: float | None = None) -> dict:
    """enforce='qr' — только в окне отметки; 'session' — до конца занятия (ручная отметка преподавателем).
    at — момент сканирования для офлайн-очереди (окно проверяется на этот момент, а не на момент отправки)."""
    s, club, start, end, original = _occurrence(db, session_id, day)
    t0, t1 = _times(day, start, end)
    now = at if at is not None else _now_ts()
    if enforce == "qr" and not (t0 - QR_EARLY <= now <= t0 + window_minutes() * 60):
        raise HTTPException(403, "Отметка закрыта" if now > t0 else "Отметка ещё не открыта")
    if enforce == "session" and not (t0 - QR_EARLY <= now <= t1):
        raise HTTPException(403, "Ручная отметка доступна только во время занятия")
    db.add(Attendance(session_id=s.id, occurrence_date=original, student_id=student_id, method=method))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Уже отмечен(а) на занятии «{club.name}»") from None
    return {"ok": True, "club_id": club.id, "club_name": club.name, "date": original, "start_time": start, "end_time": end,
            "student_id": student_id}


def _qr_payload(db: Session, session_id: int, day: str) -> dict:
    """QR открывается за 10 с до начала и выдаётся первые N минут (окно отметки); до/после — state без токена."""
    s, club, start, end, original = _occurrence(db, session_id, day)
    t0, t1 = _times(day, start, end)
    now = _now_ts()
    base = {"session_id": s.id, "club_id": club.id, "club_name": club.name, "date": day, "start_time": start, "end_time": end,
            "window_min": window_minutes(), "opens_at": datetime.fromtimestamp(t0 - QR_EARLY, MSK).isoformat(),
            "closes_at": datetime.fromtimestamp(t0 + window_minutes() * 60, MSK).isoformat()}
    if now < t0 - QR_EARLY:
        return {**base, "state": "early", "opens_in": int(t0 - QR_EARLY - now) + 1}
    if now > t0 + window_minutes() * 60:
        return {**base, "state": "closed", "manual_until": datetime.fromtimestamp(t1, MSK).isoformat()}
    token, exp = make_token(s.id, original)
    return {**base, "state": "open", "token": token, "expires_at": datetime.fromtimestamp(exp, MSK).isoformat(), "ttl": QR_TTL,
            "rotate": QR_ROTATE, "closes_in": int(t0 + window_minutes() * 60 - now)}


def _delete(db: Session, att_id: int, actor: str, session_ids: set[int] | None = None) -> None:
    row = db.get(Attendance, att_id)
    if not row or (session_ids is not None and row.session_id not in session_ids):
        raise HTTPException(404, "Отметка не найдена")
    audit.log("attendance_revoked", actor=actor, attendance_id=row.id, session_id=row.session_id, date=row.occurrence_date,
              student=short_id(row.student_id))
    db.delete(row)
    db.commit()


def _list(db: Session, session_id: int, day: str, since_id: int = 0) -> dict:
    purge(db)
    q = select(Attendance).where(Attendance.session_id == session_id, Attendance.occurrence_date == day)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.where(Attendance.id > since_id).order_by(Attendance.created_at)).all()
    return {"count": total, "items": [{"id": r.id, "student_id": r.student_id, "short": short_id(r.student_id), "method": r.method,
                                           "at": r.created_at.isoformat() + "Z"} for r in rows]}


def _history(db: Session, student_id: str) -> dict:
    purge(db)
    q = (select(Attendance, Club.name, ClubSession.start_time, ClubSession.end_time)
         .join(ClubSession, ClubSession.id == Attendance.session_id).join(Club, Club.id == ClubSession.club_id)
         .where(Attendance.student_id == student_id).order_by(Attendance.occurrence_date.desc(), ClubSession.start_time))
    return {"student_id": student_id, "retention_days": RETENTION_DAYS,
            "items": [{"club_name": n, "date": a.occurrence_date, "start_time": st, "end_time": en, "method": a.method,
                       "at": a.created_at.isoformat() + "Z"} for a, n, st, en in db.execute(q)]}


class SessionDay(BaseModel):
    session_id: int = Field(gt=0)
    date: str


class ManualMark(SessionDay):
    student_id: str

    @field_validator("student_id")
    @classmethod
    def _sid(cls, v):
        return normalize_student_id(v)


class CheckinRequest(BaseModel):
    student_id: str
    session_id: int = Field(gt=0)
    qr_token: str = Field(min_length=10, max_length=400)
    nonce: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    device_token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    # офлайн-очередь: реальный момент сканирования (unix, с). Без него — «сейчас», как раньше.
    scanned_at: float | None = Field(default=None, gt=0)

    @field_validator("student_id")
    @classmethod
    def _sid(cls, v):
        return normalize_student_id(v)


OFFLINE_MAX_DELAY = 6 * 3600   # отложенную отметку принимаем не позже 6 ч после сканирования
CLOCK_SKEW = 120               # допуск расхождения часов телефона


@router.post("/api/attendance/checkin", status_code=201)
def checkin(payload: CheckinRequest, db: Session = Depends(get_db)):
    at = None
    if payload.scanned_at is not None:
        real = _now_ts()
        if payload.scanned_at > real + CLOCK_SKEW:
            raise HTTPException(400, "Время сканирования в будущем — проверьте часы телефона")
        if payload.scanned_at < real - OFFLINE_MAX_DELAY:
            raise HTTPException(410, "Отметка из очереди слишком старая — её нельзя засчитать")
        at = min(payload.scanned_at, real)
    data = read_token(payload.qr_token, now=at)
    if at is not None and at + CLOCK_SKEW < int(data.get("i", at)):
        raise HTTPException(400, "Время сканирования раньше появления QR-кода")
    if int(data["s"]) != payload.session_id:
        raise HTTPException(409, "Этот QR-код относится к другому занятию")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if db.get(QrNonce, payload.nonce):
        raise HTTPException(409, "Повторная отправка отклонена — отсканируйте QR ещё раз")
    _device_check(db, payload.student_id, payload.device_token, register=True)
    db.add(QrNonce(nonce=payload.nonce, expires_at=now + timedelta(seconds=QR_TTL * 5 + (OFFLINE_MAX_DELAY if at else 0))))
    db.commit()
    return _record(db, int(data["s"]), data["d"], payload.student_id, "qr", enforce="qr", at=at)


def _device_check(db: Session, sid: str, token: str, register: bool = False) -> None:
    h = hashlib.sha256(token.encode()).hexdigest()
    dev = db.get(StudentDevice, sid)
    if dev is None:
        if not register:
            raise HTTPException(403, "Это устройство не подтверждено: отметьтесь хотя бы раз на занятии")
        db.add(StudentDevice(student_id=sid, token_hash=h))
        db.flush()
    elif not hmac.compare_digest(dev.token_hash, h):
        raise HTTPException(403, "ID привязан к другому устройству. Восстановите его резервным кодом.")


@router.get("/api/attendance/mine")
def mine(x_student_id: str = Header(default=""), x_device_token: str = Header(default=""), db: Session = Depends(get_db)):
    """«Мои посещения»: только со своего устройства (ID + токен устройства из первой отметки), за 21 день. Имён нет."""
    try:
        sid = normalize_student_id(x_student_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", x_device_token or ""):
        raise HTTPException(403, "Нужен токен устройства")
    _device_check(db, sid, x_device_token)
    return _history(db, sid)


@router.post("/api/admin/attendance/qr")
def create_qr(payload: SessionDay, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _qr_payload(db, payload.session_id, payload.date)


@router.post("/api/admin/attendance/manual", status_code=201)
def admin_manual(payload: ManualMark, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _record(db, payload.session_id, payload.date, payload.student_id, "manual")


@router.get("/api/admin/attendance/student")
def admin_student(student_id: str = Query(), db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """«Проверить посещение по ID» — только администратор."""
    try:
        sid = normalize_student_id(student_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return _history(db, sid)


@router.delete("/api/admin/attendance/{att_id}", status_code=204)
def admin_delete(att_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    _delete(db, att_id, f"admin:{admin.id}")


@router.get("/api/admin/attendance/stats")
def stats(
    date_from: str | None = Query(None), date_to: str | None = Query(None), club_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db), _admin=Depends(require_admin),
):
    purge(db)
    today = now_msk().date()
    try:
        d_to = date.fromisoformat(date_to) if date_to else today
        d_from = date.fromisoformat(date_from) if date_from else d_to - timedelta(days=30)
    except ValueError:
        raise HTTPException(422, "Даты в формате YYYY-MM-DD") from None
    if d_from > d_to:
        raise HTTPException(422, "date_from позже date_to")
    q = (select(Attendance.session_id, Attendance.occurrence_date, func.count(Attendance.id), ClubSession.club_id, Club.name,
                ClubSession.start_time)
         .join(ClubSession, ClubSession.id == Attendance.session_id).join(Club, Club.id == ClubSession.club_id)
         .where(Attendance.occurrence_date >= d_from.isoformat(), Attendance.occurrence_date <= d_to.isoformat())
         .group_by(Attendance.session_id, Attendance.occurrence_date)
         .order_by(Attendance.occurrence_date.desc(), ClubSession.start_time))
    if club_id:
        q = q.where(ClubSession.club_id == club_id)
    occ = [{"session_id": sid, "date": d, "count": n, "club_id": cid, "club_name": name, "start_time": st}
           for sid, d, n, cid, name, st in db.execute(q)]
    clubs: dict[int, dict] = {}
    for o in occ:
        c = clubs.setdefault(o["club_id"], {"club_id": o["club_id"], "club_name": o["club_name"], "classes": 0, "checkins": 0})
        c["classes"] += 1
        c["checkins"] += o["count"]
    for c in clubs.values():
        c["average"] = round(c["checkins"] / c["classes"], 1)
    return {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(),
            "total": sum(o["count"] for o in occ),
            "clubs": sorted(clubs.values(), key=lambda c: (-c["checkins"], c["club_name"])),
            "occurrences": occ}


@router.get("/api/admin/attendance")
def occurrence_list(session_id: int = Query(gt=0), date: str = Query(), db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _list(db, session_id, date)["items"]


@router.get("/api/admin/attendance/live")
def admin_live(session_id: int = Query(gt=0), date: str = Query(), since_id: int = Query(0, ge=0), db: Session = Depends(get_db),
               _admin=Depends(require_admin)):
    return _list(db, session_id, date, since_id)


# ---------- выгрузка посещаемости в Excel (phase 2 F)
_BAD_SHEET = str.maketrans({c: " " for c in "[]:*?/\\"})


def _sheet_title(name: str, used: set[str]) -> str:
    base = (name.translate(_BAD_SHEET).strip() or "Кружок")[:28]
    title, n = base, 2
    while title.lower() in used or title.lower() == "сводка":
        title = f"{base[:26]} {n}"
        n += 1
    used.add(title.lower())
    return title


@router.get("/api/admin/attendance/export.xlsx")
def export_xlsx(
    date_from: str | None = Query(None), date_to: str | None = Query(None), club_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db), _admin=Depends(require_admin),
):
    """Посещаемость за период: лист «Сводка» по всем (или одному) кружкам + по листу на кружок со списком отметок."""
    from io import BytesIO
    from urllib.parse import quote

    from fastapi.responses import Response
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    summary = stats(date_from=date_from, date_to=date_to, club_id=club_id, db=db, _admin=_admin)
    q = (select(Attendance, ClubSession.club_id, Club.name, ClubSession.start_time, ClubSession.end_time, Leader.name)
         .join(ClubSession, ClubSession.id == Attendance.session_id).join(Club, Club.id == ClubSession.club_id)
         .outerjoin(Leader, Leader.id == Club.leader_id)
         .where(Attendance.occurrence_date >= summary["date_from"], Attendance.occurrence_date <= summary["date_to"])
         .order_by(Club.name, Attendance.occurrence_date, ClubSession.start_time, Attendance.created_at))
    if club_id:
        q = q.where(ClubSession.club_id == club_id)
    rows: dict[int, list] = {}
    for a, cid, _name, st, en, teacher in db.execute(q):
        at = a.created_at.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%H:%M") if a.created_at else ""
        rows.setdefault(cid, []).append((a.occurrence_date, f"{st}–{en}", teacher or "", a.student_id, at))

    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка"
    bold = Font(bold=True)
    ws.append([f"Посещаемость кружков: {summary['date_from']} — {summary['date_to']}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Кружок", "Занятий с отметками", "Отметок", "В среднем на занятии"])
    for c in ws[3]:
        c.font = bold
    for c in summary["clubs"]:
        ws.append([c["club_name"], c["classes"], c["checkins"], c["average"]])
    ws.append(["Итого", sum(c["classes"] for c in summary["clubs"]), summary["total"], None])
    for c in ws[ws.max_row]:
        c.font = bold
    ws.freeze_panes = "A4"
    for i, w in enumerate((44, 22, 12, 22), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    used: set[str] = set()
    for c in summary["clubs"]:
        sh = wb.create_sheet(_sheet_title(c["club_name"], used))
        sh.append(["Дата", "Время", "Преподаватель", "ID студента", "Отметился в"])
        for cell in sh[1]:
            cell.font = bold
        for d, t, teacher, sid, at in rows.get(c["club_id"], []):
            sh.append([date.fromisoformat(d), t, teacher, sid, at])
            sh.cell(sh.max_row, 1).number_format = "DD.MM.YYYY"
        sh.freeze_panes = "A2"
        for i, w in enumerate((12, 14, 30, 40, 14), 1):
            sh.column_dimensions[get_column_letter(i)].width = w
    buf = BytesIO()
    wb.save(buf)
    name = f"attendance_{summary['date_from']}_{summary['date_to']}.xlsx"
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}",
                             "Cache-Control": "no-store"})
