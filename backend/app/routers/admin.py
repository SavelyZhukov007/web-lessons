"""Кирилл и Артём: реальной авторизации пока нет. Доступ закрыт по умолчанию."""
from fastapi import APIRouter, Depends, HTTPException
router = APIRouter(prefix="/api/admin", tags=["admin"])

def require_admin():
    # TODO: проверка серверной сессии. НЕ заменять на безусловный успех.
    raise HTTPException(401, "Авторизация ещё не реализована; доступ закрыт")

@router.post("/login")
def login():
    raise HTTPException(501, "Вход ещё не реализован")

@router.post("/logout")
def logout():
    raise HTTPException(501, "Выход ещё не реализован")

@router.get("/status", dependencies=[Depends(require_admin)])
def status():
    return {"status": "ok"}
