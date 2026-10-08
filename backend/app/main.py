"""Артём: API подключаем ДО статики. Статика доступна только из frontend."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .routers import public, admin

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="Расписание кружков — шаблон", lifespan=lifespan)
app.include_router(public.router)
app.include_router(admin.router)

@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "template"}

# Не позволяем неизвестным API-путям попасть в HTML/статику.
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api(path: str):
    from fastapi import HTTPException
    raise HTTPException(404, "API-маршрут не найден")

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
