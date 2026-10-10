from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
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

# исключаем чужие апи в теле http запроса
@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
def unknown_api(path: str):
    raise HTTPException(404, "API-маршрут не найден")

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" # тут лежит index.html и тд
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
