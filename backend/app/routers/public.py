"""Елисей, Михаил, Сергей: сейчас заглушки 501. Заменять по api-contract.md."""
from fastapi import APIRouter, HTTPException
router = APIRouter(prefix="/api", tags=["public"])

def pending():
    raise HTTPException(501, "Заглушка: маршрут ещё не реализован")

@router.get("/categories")
def categories(): return pending()

@router.get("/leaders")
def leaders(): return pending()

@router.get("/rooms")
def rooms(): return pending()

@router.get("/clubs")
def clubs(search: str | None = None, category_id: int | None = None):
    return pending()

@router.get("/clubs/{club_id}")
def club(club_id: int): return pending()

@router.get("/schedule")
def schedule(week: str): return pending()
