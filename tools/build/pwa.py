from __future__ import annotations

import json
import shutil
from pathlib import Path

from .common import ROOT, copy_tree, output_dir, stamp_web


def build_pwa(out: Path | None = None) -> Path:
    dest = output_dir("pwa", out)
    copy_tree(ROOT / "frontend", dest, exclude={"mock-data.json", "new.html", "initial.css"})
    copy_tree(ROOT / "pwa", dest / "pwa")
    shim = ROOT / "android/shim"
    for name in ("native-shell.js", "native-features.js", "native-motion.js", "qr-checkin.js", "app-student.js", "app-admin.js"):
        shutil.copy2(shim / name, dest / "js" / name)
    for name in ("native-shell.css", "native-features.css", "native-motion.css", "app-student.css"):
        shutil.copy2(shim / name, dest / "css" / name)
    shutil.copy2(shim / "qr.html", dest / "qr.html")
    # Vendored jsQR + Apache license: a clean checkout needs no npm install to build PWA.
    shutil.copy2(ROOT / "frontend/js/vendor/jsQR.js", dest / "js/jsQR.js")
    manifest_path = dest / "manifest.webmanifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shortcuts"] = [{"name": "Мои кружки", "url": "/?my=1"},
                             {"name": "Отметиться", "url": "/qr.html?source=shortcut"},
                             *manifest.get("shortcuts", [])]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in dest.rglob("*.html"):
        html = path.read_text(encoding="utf-8")
        html = html.replace("</head>", '    <script src="/pwa/pwa-standalone.js"></script>\n</head>')
        path.write_text(html, encoding="utf-8")
    stamp_web(dest)
    print(f"PWA собрано: {dest}. Safari → Поделиться → Добавить на экран Домой.")
    return dest
