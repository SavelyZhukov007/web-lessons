from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER = ".clubs-build.json"


class BuildError(Exception):
    """An actionable build failure, without an internal traceback."""


def python_version_ok() -> None:
    if sys.version_info < (3, 10):
        raise BuildError("Нужен Python 3.10 или новее.")


def output_dir(target: str, out: Path | None) -> Path:
    path = (out or ROOT / "builds" / target).absolute()
    resolved = path.resolve()
    protected = [ROOT, *(ROOT / name for name in ("frontend", "backend", "tools", "pwa", "android", "data", "deploy", "docs"))]
    if path.is_symlink() or any(resolved == p or resolved in p.parents or p in resolved.parents for p in protected[1:]):
        raise BuildError("Каталог сборки пересекается с исходниками.")
    if resolved == ROOT or resolved in ROOT.parents:
        raise BuildError("Нельзя собирать поверх проекта или его родительского каталога.")
    if path.exists() and any(path.iterdir()):
        marker = path / MARKER
        try:
            owned = marker.is_file() and json.loads(marker.read_text(encoding="utf-8")).get("target") == target
        except (OSError, ValueError):
            owned = False
        if not owned:
            raise BuildError(f"Каталог не пуст и не является сборкой {target}: {path}. Выберите другой --out.")
        # Only an explicitly selected, marked build directory may be replaced.
        if path.resolve() != resolved:
            raise BuildError("Каталог сборки изменился.")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER).write_text(json.dumps({"target": target}), encoding="utf-8")
    return path


def copy_tree(src: Path, dest: Path, *, exclude: set[str] | None = None) -> None:
    exclude = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "tests", ".env", "jwt_secret.key", "vapid_keys.json", *(exclude or set())}
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if any(part in exclude or part.startswith(".") for part in rel.parts) or path.is_symlink():
            continue
        if not path.is_file() or path.suffix in {".pyc", ".map", ".key", ".sqlite3", ".jks", ".keystore"} or path.name.endswith((".test.mjs", "-wal", "-shm")):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def stamp_web(out: Path) -> None:
    files = [p for p in sorted(out.rglob("*")) if p.is_file() and p.name not in {"sw.js", MARKER, "build-info.json"}]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(out).as_posix().encode())
        digest.update(path.read_bytes())
    # Changes to worker code also invalidate the cache.
    worker = (ROOT / "frontend/sw.js").read_text(encoding="utf-8")
    digest.update(worker.encode())
    build_id = digest.hexdigest()[:20]
    urls = ["/"] + ["/" + p.relative_to(out).as_posix() for p in files if not p.relative_to(out).as_posix().startswith("admin/")]
    lines = worker.splitlines()
    for i, line in enumerate(lines):
        if "// __BUILD_ID__" in line:
            lines[i] = f"const BUILD_ID = {json.dumps(build_id)}; // __BUILD_ID__"
        elif "// __PRECACHE__" in line:
            lines[i] = f"const PRECACHE = {json.dumps(urls, ensure_ascii=False)}; // __PRECACHE__"
    if (out / "pwa/sw-pwa.js").exists():
        lines.append("importScripts('/pwa/sw-pwa.js');")
    (out / "sw.js").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "build-info.json").write_text(json.dumps({"build_id": build_id}, indent=2) + "\n", encoding="utf-8")
