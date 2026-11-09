"""Покрытие JS-кода pwa/ по данным V8 (CDP Profiler в Chromium и NODE_V8_COVERAGE в node).
Строка считается покрытой, если все её значимые символы выполнялись хотя бы в одном снимке; пустые строки и
строки-комментарии не учитываются. Снимки страницы снимаются перед каждой навигацией и перед закрытием контекста."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PWA_FILES = ("pwa-features.js", "pwa-standalone.js", "sw-pwa.js")


def _counts(length: int, functions: list[dict]) -> list[int]:
    ranges = sorted((r for f in functions for r in f["ranges"]), key=lambda r: (r["startOffset"], -r["endOffset"]))
    counts = [1] * length  # вне диапазонов V8 — код верхнего уровня скрипта, он выполнен
    for r in ranges:
        for i in range(max(0, r["startOffset"]), min(length, r["endOffset"])):
            counts[i] = r["count"]
    return counts


class Coverage:
    def __init__(self):
        self.executed: dict[str, list[bool]] = {}

    def add(self, name: str, source: str, functions: list[dict]) -> None:
        counts = _counts(len(source), functions)
        seen = self.executed.setdefault(name, [False] * len(source))
        if len(seen) != len(source):
            return  # другой вариант файла — пропускаем
        for i, c in enumerate(counts):
            if c > 0:
                seen[i] = True

    def add_v8(self, entries: list[dict], sources: dict[str, str] | None = None) -> None:
        for entry in entries:
            name = next((n for n in PWA_FILES if entry.get("url", "").split("?")[0].endswith("/pwa/" + n)), None)
            if not name:
                continue
            source = (sources or {}).get(entry["url"]) or (ROOT / "pwa" / name).read_text(encoding="utf-8")
            self.add(name, source, entry["functions"])

    def report(self) -> dict[str, tuple[int, int]]:
        out = {}
        for name in PWA_FILES:
            source = (ROOT / "pwa" / name).read_text(encoding="utf-8")
            seen = self.executed.get(name)
            total = covered = 0
            offset = 0
            in_comment = False
            for line in source.splitlines(keepends=True):
                text = line.strip()
                start = offset
                offset += len(line)
                if in_comment:
                    in_comment = "*/" not in text
                    continue
                if not text or text.startswith("//"):
                    continue
                if text.startswith("/*"):
                    in_comment = "*/" not in text
                    continue
                total += 1
                if seen and all(seen[i] for i in range(start, start + len(line)) if i < len(seen) and not line[i - start].isspace()):
                    covered += 1
            out[name] = (covered, total)
        return out

    def percent(self) -> float:
        rows = self.report().values()
        total = sum(t for _, t in rows)
        return 100.0 * sum(c for c, _ in rows) / total if total else 100.0


class PageCoverage:
    """Подключается к страницам контекста Playwright (sync API)."""

    def __init__(self, coverage: Coverage):
        self.coverage = coverage
        self.sessions = []

    def attach_context(self, context):
        context.on("page", self.attach)
        close = context.close

        def close_with_snapshot(*a, **kw):
            for page, _ in list(self.sessions):
                if not page.is_closed():
                    self.snapshot(page)
            self.sessions = [(p, s) for p, s in self.sessions if p.context is not context]
            return close(*a, **kw)
        context.close = close_with_snapshot
        return context

    def attach(self, page):
        session = page.context.new_cdp_session(page)
        session.send("Profiler.enable")
        session.send("Profiler.startPreciseCoverage", {"callCount": False, "detailed": True})
        self.sessions.append((page, session))
        for method in ("goto", "reload"):
            original = getattr(page, method)

            def wrapped(*a, _original=original, **kw):
                self.snapshot(page)
                return _original(*a, **kw)
            setattr(page, method, wrapped)

    def snapshot(self, page):
        session = next((s for p, s in self.sessions if p is page), None)
        if session is None:
            return
        try:
            result = session.send("Profiler.takePreciseCoverage")["result"]
        except Exception:  # noqa: BLE001 — страница могла уже уйти
            return
        wanted = [e for e in result if "/pwa/" in e.get("url", "")]
        sources = {}
        for entry in wanted:
            try:
                session.send("Debugger.enable")
                sources[entry["url"]] = session.send("Debugger.getScriptSource", {"scriptId": entry["scriptId"]})["scriptSource"]
            except Exception:  # noqa: BLE001
                pass
        self.coverage.add_v8(wanted, sources)


def run_node_tests(coverage: Coverage) -> bool:
    """node-тесты service worker pwa/sw-pwa.js с NODE_V8_COVERAGE."""
    tests = sorted(str(p) for p in (ROOT / "pwa/tests").glob("*.test.mjs"))
    if not tests:
        return True
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(["node", "--test", *tests], cwd=ROOT, env={**os.environ, "NODE_V8_COVERAGE": tmp},
                              capture_output=True, text=True, timeout=120)
        print(proc.stdout[-1500:] if proc.returncode else re.sub(r"(?s).*(ℹ tests.*?ℹ fail \d+).*", r"\1", proc.stdout))
        for file in Path(tmp).glob("*.json"):
            coverage.add_v8(json.loads(file.read_text(encoding="utf-8")).get("result", []))
    return proc.returncode == 0
