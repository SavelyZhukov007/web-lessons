from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .common import ROOT, BuildError


def publish_release(apk: Path, out: Path | None = None) -> Path:
    dest = out or Path(os.getenv("APP_RELEASES_DIR") or ROOT / "releases/android")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / apk.name
    if apk.resolve() != target.resolve():
        shutil.copy2(apk, target)
    version = json.loads((ROOT / "android/version.json").read_text(encoding="utf-8"))
    shared = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    meta = {"file": target.name, "version": version.get("versionName") or shared.get("version"),
            "versionCode": version["versionCode"], "minSupported": version.get("minSupported", 1),
            "changelog": version.get("changelog", []), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    staging = dest / "latest.json.tmp"
    staging.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staging.replace(dest / "latest.json")
    return target


def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise BuildError("Не найден Node.js в PATH. Установите Node.js и откройте терминал заново.")
    return node


def build_android(*, server_url=None, install=False, check_only=False, demo=False, with_demo=True, publish=True):
    node = _node()
    args = [node, "scripts/build-apk.mjs", "--no-bump"]
    if check_only:
        args.append("--check-only")
    if server_url:
        args += ["--server-url", server_url]
    if install:
        args.append("--install")
    if demo:
        args.append("--demo")
    result = subprocess.run(args, cwd=ROOT / "android", check=False)
    if result.returncode:
        raise BuildError(f"Android сборка завершилась с кодом {result.returncode}; подробности выше.")
    if check_only:
        return None
    apks = sorted((ROOT / "android/dist").glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not apks:
        raise BuildError("Скрипт Android не создал APK.")
    apk = apks[0]
    # Debug/demo packages are never silently promoted to a public release.
    if publish and os.getenv("ANDROID_PUBLISH_DEBUG") == "1":
        publish_release(apk)
    if with_demo and not demo:
        build_android(server_url=server_url, demo=True, with_demo=False, publish=False)
    return apk


def build_demo_web(out: Path | None = None) -> Path:
    from .common import MARKER, output_dir
    dest = output_dir("web-demo", out)
    env = {**os.environ, "APP_DEMO": "1", "WWW_OUT": str(dest)}
    result = subprocess.run([_node(), "scripts/prepare-web.mjs"], cwd=ROOT / "android", env=env, check=False)
    if result.returncode:
        raise BuildError("Не удалось собрать web demo; проверьте npm ci в android/.")
    (dest / MARKER).write_text(json.dumps({"target": "web-demo"}), encoding="utf-8")
    return dest
