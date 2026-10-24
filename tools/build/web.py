from __future__ import annotations

from pathlib import Path

from .common import ROOT, copy_tree, output_dir, stamp_web


def build_web(out: Path | None = None) -> Path:
    dest = output_dir("web", out)
    copy_tree(ROOT / "frontend", dest, exclude={"mock-data.json", "new.html", "initial.css"})
    stamp_web(dest)
    print(f"Сайт собран: {dest}")
    return dest
