"""Запуск из корня: python server.py. Это единый сервер страниц и API."""
if __name__ == "__main__":
    from pathlib import Path
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000,
                reload=True, app_dir=str(Path(__file__).resolve().parent))
