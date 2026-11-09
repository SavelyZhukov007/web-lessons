"""Content-versioned graph: relative JS imports stay inside one immutable build directory."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

STATIC = {".js", ".css", ".woff2", ".png", ".svg", ".ico"}
PATH = re.compile(r"([\"'`(])/(js|css|fonts|icons|vendor|pwa)/")
def fingerprint_assets(out: Path) -> str:
    files = [p for p in sorted(out.rglob("*")) if p.is_file() and p.suffix in STATIC
             and p.name != "sw.js" and "assets" not in p.relative_to(out).parts
             and "admin" not in p.relative_to(out).parts[:1]]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(out).as_posix().encode()); digest.update(path.read_bytes())
    version = digest.hexdigest()[:20]
    root = f"/assets/{version}"
    # Include admin JS too (lazy routes); never include admin HTML or private API responses.
    source = [p for p in sorted(out.rglob("*")) if p.is_file() and p.suffix in STATIC
              and p.name != "sw.js" and "assets" not in p.relative_to(out).parts]
    for path in source:
        rel = path.relative_to(out); target = out / "assets" / version / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in {".js", ".css"}:
            text = PATH.sub(lambda match: match[1] + root + "/" + match[2] + "/", path.read_text(encoding="utf-8"))
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(path, target)
    for path in out.rglob("*.html"):
        text = PATH.sub(lambda match: match[1] + root + "/" + match[2] + "/", path.read_text(encoding="utf-8"))
        path.write_text(text, encoding="utf-8")
    return version
