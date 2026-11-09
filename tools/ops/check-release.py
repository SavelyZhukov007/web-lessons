"""Verify a deployed build, or start an isolated candidate for the same checks."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def check(base, build, revision, manifest, *, host=None, candidate=None):
    def request(path, timeout=10):
        headers = {"Host": host} if host else {}
        return urlopen(Request(base + path, headers=headers), timeout=timeout)

    def read(path):
        with request(path) as response:
            return json.load(response)

    for attempt in range(45):
        if candidate is not None and candidate.poll() is not None:
            raise RuntimeError(f"Candidate exited with status {candidate.returncode}")
        try:
            if read("/readyz") == {"status": "ready", "revision": revision}:
                break
        except OSError:
            pass
        if attempt == 44:
            raise RuntimeError(f"{base} is not ready on revision {revision}")
        time.sleep(2)
    if read("/build-info.json")["build_id"] != build:
        raise RuntimeError(f"{base} is serving a different build")
    if manifest is None:
        return
    today = date.today()
    week = today - timedelta(days=today.weekday())
    schedule = read(f"/api/week?week={week.isoformat()}")
    if not isinstance(schedule["events"], list):
        raise RuntimeError(f"{base} did not return a schedule")
    try:
        with request("/api/admin/status"):
            raise RuntimeError(f"{base} allowed unauthenticated access to admin status")
    except HTTPError as exc:
        if exc.code != 401:
            raise
    if read("/manifest.webmanifest").get("display") != "standalone":
        raise RuntimeError(f"{base} is missing the standalone manifest")
    with request("/sw.js") as response:
        if build.encode() not in response.read():
            raise RuntimeError(f"{base} is serving a different service worker")
    live = read("/api/app/android")
    if any(live.get(key) != manifest[key] for key in ("file", "versionName", "versionCode", "sha256", "size", "changelog")):
        raise RuntimeError(f"{base} is serving a different APK manifest")
    with request("/android/download", timeout=30) as response:
        digest = hashlib.sha256()
        size = 0
        for chunk in iter(lambda: response.read(128 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size != manifest["size"] or digest.hexdigest() != manifest["sha256"]:
        raise RuntimeError(f"{base} is serving different APK bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("build")
    parser.add_argument("revision")
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
    base = args.url.rstrip("/")
    if not args.candidate:
        check(base, args.build, args.revision, manifest)
        return
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        env={**os.environ, "CLUBS_DEPLOY_CHECK": "1"},
    )
    try:
        check("http://127.0.0.1:8000", args.build, args.revision, manifest, host=urlsplit(base).hostname, candidate=proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
