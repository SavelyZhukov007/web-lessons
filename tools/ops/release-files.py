"""Verify staged APK bytes and switch the published manifest atomically."""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def install(src, dst):
    tmp = dst.with_name(dst.name + ".new")
    shutil.copyfile(src, tmp)
    tmp.chmod(0o644)
    tmp.replace(dst)


def main():
    stage, action, *args = sys.argv[1:]
    stage = Path(stage)
    releases = Path(os.environ["APP_RELEASES_DIR"])
    latest = releases / "latest.json"
    previous = releases / "latest.before-release.json"
    staged = stage / "latest.json"
    if action == "stage":
        name, code, version = args
        new, old = read(staged), read(latest)
        notes = read(stage / "source/frontend/release-info.json")
        apk = stage / name
        digest = hashlib.sha256(apk.read_bytes()).hexdigest()
        if not (
            new["file"] == name
            and new["versionName"] == name.removeprefix("kipclub-").removesuffix(".apk")
            and new["versionCode"] == int(code) > int(old["versionCode"])
            and new["size"] == apk.stat().st_size
            and new["sha256"] == digest
            and notes["version"] == version
            and notes["announcement"] == new["announcement"] == "auto"
            and notes["changelog"] == new["changelog"]
        ):
            raise ValueError("Staged APK or release notes do not match the requested upgrade")
        install(latest, previous)
        install(apk, releases / name)
    elif action == "publish":
        install(staged, latest)
    elif action == "rollback":
        install(previous, latest)
    else:
        raise ValueError(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
