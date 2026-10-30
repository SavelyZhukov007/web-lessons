#!/usr/bin/env python3
"""Выгрузка «Обратной связи» с сервера на компьютер разработчика — по SSH, только чтение.

На сервере отчёты лежат папками в /data/feedback контейнера app (именованный том clubs_clubs-data;
пользователю SSH напрямую он не доступен, поэтому чтение идёт через
`docker compose -f /opt/clubs/docker-compose.yml exec -T app …`). Сервер хранит последние FEEDBACK_KEEP (50).

Скрипт сравнивает папки на сервере с QA/<server>/ по id отчёта и sha256 из manifest.json, скачивает только
новые/изменённые, проверяет хэши и обновляет QA/<server>/index.csv и QA/README.md. Ничего на сервере не меняет
и не удаляет; локально хранится всё, что когда-либо скачано (даже если сервер уже удалил старые).

    python tools/feedback_export.py --server test
    python tools/feedback_export.py --server prod --host <ip> --key ~/.ssh/id_ed25519
    python tools/feedback_export.py --server test --dry-run          # только показать, что будет скачано
    python tools/feedback_export.py --server test --local-remote D:/copy/feedback   # проверка без SSH

SSH: paramiko, если установлен, иначе системные ssh (Windows OpenSSH подходит). Нужен ключ без пароля или ssh-agent.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import posixpath
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = {
    "test": {"host": "185.53.233.170", "user": "savely-server", "port": 22},
    "prod": {"host": None, "user": "savely-server", "port": 22},
}
DEFAULT_REMOTE_DIR = "/data/feedback"
DEFAULT_COMPOSE = "/opt/clubs/docker-compose.yml"
MANIFEST = "manifest.json"

# Выполняется на сервере (python3 хоста или контейнера): JSON со всеми manifest готовых папок.
LIST_CODE = r'''
import json, os, sys
d = sys.argv[1]
out = {"exists": os.path.isdir(d), "reports": []}
if out["exists"]:
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n, "manifest.json")
        if n.startswith(".") or not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
        except Exception as e:
            out["reports"].append({"folder": n, "error": str(e)[:200]})
            continue
        m["folder"] = n
        out["reports"].append(m)
sys.stdout.write(json.dumps(out))
'''


class ExportError(RuntimeError):
    pass


# ---------- выполнение команд на «сервере» ----------

class LocalRunner:
    """Имитация сервера: команды выполняются локально (для проверки без SSH)."""
    label = "local"

    def run(self, cmd: list[str]) -> bytes:
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode:
            raise ExportError(f"{cmd[0]}: {r.stderr.decode('utf-8', 'replace').strip()[:500]}")
        return r.stdout

    def close(self):
        pass


class SshRunner:
    def __init__(self, host: str, user: str, port: int, key: str | None, timeout: int = 20):
        self.host, self.user, self.port, self.key, self.timeout = host, user, port, key, timeout
        self.client = None
        try:
            import paramiko  # noqa: F401
            self.label = "paramiko"
        except ImportError:
            if not shutil.which("ssh"):
                raise ExportError("Нет ни paramiko, ни команды ssh (Windows: «Клиент OpenSSH» в дополнительных компонентах)") from None
            self.label = "ssh"

    def _paramiko(self):
        if self.client is None:
            import paramiko
            c = paramiko.SSHClient()
            c.load_system_host_keys()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                c.connect(self.host, self.port, self.user, key_filename=self.key, timeout=self.timeout)
            except Exception as e:
                raise ExportError(f"SSH {self.user}@{self.host}:{self.port}: {e}") from None
            self.client = c
        return self.client

    def run(self, cmd: list[str]) -> bytes:
        line = " ".join(shlex.quote(c) for c in cmd)
        if self.label == "paramiko":
            _, out, err = self._paramiko().exec_command(line)
            data = out.read()
            code = out.channel.recv_exit_status()
            if code:
                raise ExportError(f"сервер: {err.read().decode('utf-8', 'replace').strip()[:500]}")
            return data
        args = ["ssh", "-p", str(self.port), "-o", "BatchMode=yes", "-o", f"ConnectTimeout={self.timeout}"]
        if self.key:
            args += ["-i", self.key]
        r = subprocess.run(args + [f"{self.user}@{self.host}", line], capture_output=True)
        if r.returncode:
            raise ExportError(f"ssh: {r.stderr.decode('utf-8', 'replace').strip()[:500]}")
        return r.stdout

    def close(self):
        if self.client:
            self.client.close()


class Remote:
    """Доступ к папке отчётов: напрямую (direct) или через контейнер (docker). Только чтение."""

    def __init__(self, runner, remote_dir: str, mode: str, compose: str, service: str = "app", python: str = "python3"):
        self.runner, self.dir, self.compose, self.service, self.python = runner, remote_dir, compose, service, python
        if mode == "auto":
            probe = runner.run(["sh", "-c", 'test -d "$1" -a -r "$1" -a -x "$1" && echo direct || echo docker', "sh", remote_dir])
            mode = probe.decode().strip() or "docker"
        self.mode = mode

    def _cmd(self, cmd: list[str]) -> list[str]:
        if self.mode == "docker":
            return ["docker", "compose", "-f", self.compose, "exec", "-T", self.service, *cmd]
        return cmd

    def list(self) -> dict:
        raw = self.runner.run(self._cmd([self.python, "-c", LIST_CODE, self.dir]))
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ExportError(f"Непонятный ответ сервера: {raw[:200]!r}") from None

    def tar(self, folders: list[str]) -> bytes:
        return self.runner.run(self._cmd(["tar", "-C", self.dir, "-cf", "-", "--", *folders]))


# ---------- локальная сторона ----------

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(folder: Path, manifest: dict) -> list[str]:
    """Проблемы папки относительно manifest (пусто — всё совпало)."""
    bad = []
    files = manifest.get("files") or {}
    for rel, info in files.items():
        p = folder / rel
        if not p.is_file():
            bad.append(f"нет {rel}")
        elif p.stat().st_size != info.get("size") or sha256_file(p) != info.get("sha256"):
            bad.append(f"хэш {rel}")
    for p in folder.rglob("*"):
        rel = p.relative_to(folder).as_posix()
        if p.is_file() and rel != MANIFEST and rel not in files:
            bad.append(f"лишний {rel}")
    return bad


def local_reports(base: Path) -> dict[str, dict]:
    out = {}
    if base.is_dir():
        for p in sorted(base.iterdir()):
            m = p / MANIFEST
            if p.is_dir() and not p.name.startswith(".") and m.is_file():
                try:
                    man = json.loads(m.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                if man.get("id"):
                    out[man["id"]] = {"path": p, "manifest": man}
    return out


def _safe_name(n: str) -> bool:
    return bool(n) and "/" not in n and "\\" not in n and n not in (".", "..") and not n.startswith(".")


def extract(tar_bytes: bytes, dest: Path, folders: set[str]) -> None:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tf:
        for m in tf.getmembers():
            name = posixpath.normpath(m.name)
            top = name.split("/", 1)[0]
            if name.startswith(("/", "..")) or top not in folders or not (m.isfile() or m.isdir()):
                raise ExportError(f"Подозрительный путь в архиве: {m.name}")
            target = dest.joinpath(*name.split("/"))
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def plan(remote: list[dict], local: dict[str, dict]) -> tuple[list[dict], list[dict], list[dict]]:
    new, changed, same = [], [], []
    for m in remote:
        if "error" in m or not m.get("id") or not _safe_name(m["folder"]):
            continue
        have = local.get(m["id"])
        if not have:
            new.append(m)
        elif have["manifest"].get("files") != m.get("files") or verify(have["path"], have["manifest"]):
            changed.append(m)
        else:
            same.append(m)
    return new, changed, same


def write_index(base: Path, on_server: set[str]) -> int:
    rows = []
    for rid, r in sorted(local_reports(base).items(), key=lambda kv: kv[1]["path"].name):
        p = r["path"]
        try:
            rep = json.loads((p / "report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rep = {}
        desc = ""
        dpath = p / "description.md"
        if dpath.is_file():
            lines = [ln.strip() for ln in dpath.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
            desc = (lines[0] if lines else "")[:120]
        rows.append({"folder": p.name, "id": rid, "created_at": r["manifest"].get("created_at", ""), "type": rep.get("type", ""),
                     "app_version": rep.get("app_version", ""), "platform": rep.get("platform", ""), "contact": rep.get("contact") or "",
                     "screenshots": len(rep.get("screenshots") or []), "on_server": "yes" if rid in on_server else "no", "description": desc})
    with (base / "index.csv").open("w", newline="", encoding="utf-8-sig") as f:  # BOM — чтобы Excel открыл кириллицу
        w = csv.DictWriter(f, fieldnames=["folder", "id", "created_at", "type", "app_version", "platform", "contact", "screenshots", "on_server", "description"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


README = """# QA — обращения «Обратная связь»

Эта папка заполняется скриптом `tools/feedback_export.py` (или `tools/feedback_export.ps1`) и в git не попадает (`.gitignore`).

- `test/` — отчёты, скачанные с тестового сервера (185.53.233.170);
- `prod/` — отчёты, скачанные с боевого сервера.

Внутри — папка на каждое обращение: `<ГГГГ-ММ-ДД_ЧЧММСС>_<тип>_<id>/` (время UTC) с файлами
`description.md` (текст), `report.json` (версия, устройство, контакт), `logs.json` (журнал ошибок, без паролей
и личных данных), `screenshots/01.png…` и `manifest.json` (полный id, sha256 и размер каждого файла).
`index.csv` — сводная таблица; колонка `on_server` показывает, есть ли отчёт на сервере на момент последней выгрузки.

Сервер хранит только последние 50 обращений; здесь остаётся всё, что когда-либо было скачано.
Повторный запуск скачивает только новые или изменённые отчёты (сравнение по id и sha256) и ничего не меняет на сервере.
"""


def export(remote: Remote, out_root: Path, server: str, dry_run: bool = False, log=print) -> dict:
    base = out_root / server
    listing = remote.list()
    reports = listing.get("reports", [])
    for m in reports:
        if "error" in m:
            log(f"  ! {m['folder']}: битый manifest ({m['error']}) — пропускаю")
    local = local_reports(base)
    new, changed, same = plan(reports, local)
    log(f"Сервер: {len(reports)} отчётов ({remote.mode}{'' if listing.get('exists') else ', папки ещё нет'}); локально: {len(local)}; "
        f"новых: {len(new)}, изменённых: {len(changed)}, без изменений: {len(same)}")
    todo = new + changed
    result = {"new": [m["folder"] for m in new], "changed": [m["folder"] for m in changed], "same": len(same), "failed": []}
    if dry_run:
        for m in todo:
            log(f"  would download {m['folder']}")
        return result
    base.mkdir(parents=True, exist_ok=True)
    if todo:
        with tempfile.TemporaryDirectory(dir=base, prefix=".dl-") as tmp:
            tmp = Path(tmp)
            extract(remote.tar([m["folder"] for m in todo]), tmp, {m["folder"] for m in todo})
            for m in todo:
                got = tmp / m["folder"]
                problems = verify(got, m) if got.is_dir() else ["папка не пришла"]
                if problems:
                    log(f"  ! {m['folder']}: не сошлось ({', '.join(problems[:3])}) — не сохраняю")
                    result["failed"].append(m["folder"])
                    continue
                old = local.get(m["id"])
                if old:
                    keep = base / ".replaced" / f"{old['path'].name}.{datetime.now():%Y%m%d-%H%M%S}"
                    keep.parent.mkdir(exist_ok=True)
                    shutil.move(str(old["path"]), str(keep))
                dest = base / m["folder"]
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(got), str(dest))
                log(f"  + {m['folder']}" + ("  (обновлён)" if old else ""))
    on_server = {m["id"] for m in reports if m.get("id")}
    n = write_index(base, on_server)
    (out_root / "README.md").write_text(README, encoding="utf-8")
    log(f"Готово: {base} ({n} отчётов в index.csv)")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Скачать новые обращения «Обратная связь» с сервера по SSH (только чтение).")
    ap.add_argument("--server", choices=sorted(SERVERS), default="test")
    ap.add_argument("--host")
    ap.add_argument("--user")
    ap.add_argument("--port", type=int)
    ap.add_argument("--key", help="приватный ключ SSH (по умолчанию — ssh-agent / ~/.ssh)")
    ap.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="папка отчётов (в контейнере для docker-режима)")
    ap.add_argument("--mode", choices=["auto", "direct", "docker"], default="auto",
                    help="direct — папка читается пользователем SSH; docker — через docker compose exec (auto — проверить)")
    ap.add_argument("--compose", default=DEFAULT_COMPOSE)
    ap.add_argument("--service", default="app")
    ap.add_argument("--out", default=str(ROOT / "QA"), help="корень локальной папки (по умолчанию QA/ в репозитории)")
    ap.add_argument("--local-remote", metavar="DIR", help="проверка без SSH: считать «сервером» локальную папку")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cfg = dict(SERVERS[a.server])
    host, user, port = a.host or cfg["host"], a.user or cfg["user"], a.port or cfg["port"]
    try:
        if a.local_remote:
            runner, remote_dir, mode = LocalRunner(), str(Path(a.local_remote).resolve()), "direct"
            print(f"[{a.server}] имитация сервера: {remote_dir}")
        else:
            if not host:
                raise ExportError(f"Для --server {a.server} укажите --host")
            key = os.path.expanduser(a.key) if a.key else None
            runner, remote_dir, mode = SshRunner(host, user, port, key), a.remote_dir, a.mode
            print(f"[{a.server}] {user}@{host}:{port} через {runner.label}")
        try:
            remote = Remote(runner, remote_dir, mode, a.compose, a.service, python=sys.executable if a.local_remote else "python3")
            res = export(remote, Path(a.out), a.server, a.dry_run)
        finally:
            runner.close()
    except ExportError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
