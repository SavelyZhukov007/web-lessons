from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import ROOT, copy_tree, output_dir
from .web import build_web


def build_back(out: Path | None = None) -> Path:
    dest = output_dir("back", out)
    pkg = dest / "clubs-backend"
    pkg.mkdir()
    copy_tree(ROOT / "backend", pkg / "backend", exclude={"requirements-dev.txt", "requirements-dev.lock.txt"})
    copy_tree(ROOT / "tools", pkg / "tools")
    copy_tree(ROOT / "deploy", pkg / "deploy")
    shutil.copy2(ROOT / "deploy/.env.example", pkg / "deploy/.env.example")
    (pkg / "data").mkdir()
    for name in ("demo-data.json", "sample-data.json"):
        shutil.copy2(ROOT / "data" / name, pkg / "data" / name)
    for name in ("server.py", "pyproject.toml"):
        shutil.copy2(ROOT / name, pkg / name)
    shutil.copy2(ROOT / "version.json", pkg / "version.json")
    (pkg / "android").mkdir()
    shutil.copy2(ROOT / "android/version.json", pkg / "android/version.json")
    build_web(pkg / "web")
    (pkg / "RUN.md").write_text(
        "# Запуск релиза\n\nPython 3.10+; отдельное виртуальное окружение.\n\n"
        "    python -m pip install -r backend/requirements.lock.txt\n\n"
        "Настройте ENV=production, JWT_SECRET, ALLOWED_HOSTS и CLUBS_SCHEDULE_DB_PATH вне пакета.\n"
        "Пример переменных: deploy/.env.example. Переменные должны быть экспортированы в окружение процесса.\n\n"
        "    python server.py check-config\n"
        "    python server.py serve --frontend web --host 0.0.0.0 --port 8000 --no-reload\n\n"
        "Перед сервером нужен HTTPS reverse proxy. Один worker; БД и секреты хранить в постоянном томе.\n",
        encoding="utf-8",
    )
    archive = Path(shutil.make_archive(str(dest / "clubs-backend"), "zip", dest, "clubs-backend"))
    (dest / "clubs-backend.zip.sha256").write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
    print(f"Backend пакет: {archive}")
    return archive
