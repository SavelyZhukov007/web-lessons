#!/usr/bin/env python3
"""Стресс/нагрузочный тест KipClub (только ГОСТИ, только чтение).

Ступенчатый рост одновременных виртуальных пользователей; каждый пользователь
ходит по реальным публичным страницам/API с паузами «на чтение». Тест сам
останавливается при перегрузке (или по лимиту времени / пользователей / Ctrl+C)
и печатает отчёт: зоны «комфортно / нормально / перебор» и оценку аудитории.

Зависимость: aiohttp (уже стоит вместе с backend: pywebpush -> aiohttp).
    pip install aiohttp

Примеры:
    python tools/stress/stress_test.py                          # локально, http://127.0.0.1:8000
    python tools/stress/stress_test.py --url http://lekora.ru:7443 --host-header lekora.ru:7443 --yes-prod
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

# --------------------------------------------------------------------------- сценарий
# Все маршруты сверены с backend/app/routers/{public,announcements,app_api,push}.py и main.py.
# Только GET. Никаких /api/admin, POST, push-подписок, рассылок. /api/announcements — БЕЗ device
# (с device сервер пишет «touch_device» в БД — это уже запись).
PAGE_ASSETS = {
    "/": ["/css/tokens.css", "/css/campus.css?v=kc6", "/css/components.css", "/css/platform.css",
          "/css/schedule.css?v=kc6", "/js/theme-init.js", "/js/settings.js", "/js/schedule.js",
          "/js/install-banner.js", "/js/pwa-register.js"],
    "/clubs.html": ["/css/tokens.css", "/css/campus.css?v=kc6", "/css/components.css", "/css/pages.css",
                    "/css/platform.css", "/js/theme-init.js", "/js/settings.js", "/js/clubs.js",
                    "/js/install-banner.js", "/js/pwa-register.js"],
}
# (вес, имя, путь); {club} подставляется из /api/clubs
ACTIONS = [
    (30, "api_schedule", "/api/schedule?week={week}"),
    (8, "api_schedule_day", "/api/schedule?week={week}&weekday={weekday}"),
    (12, "api_clubs", "/api/clubs"),
    (12, "api_club", "/api/clubs/{club}"),
    (6, "api_categories", "/api/categories"),
    (4, "api_leaders", "/api/leaders"),
    (3, "api_rooms", "/api/rooms"),
    (8, "api_announcements", "/api/announcements?since=0"),
    (3, "api_app_info", "/api/app/info"),
    (6, "page_index", "/"),
    (5, "page_clubs", "/clubs.html"),
    (2, "page_club", "/club.html"),
    (1, "page_install", "/install"),
]
STATIC_SAMPLE = 0.15  # доля «холодных» заходов, когда браузер заново тянет css/js (иначе — из кэша)


def endpoint_label(path: str) -> str:
    return path.split("?")[0]


# --------------------------------------------------------------------------- статистика
@dataclass
class StepStats:
    users: int
    started: float = 0.0
    duration: float = 0.0
    lat: list[float] = field(default_factory=list)
    ok: int = 0
    bytes: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    per_ep: dict[str, list[float]] = field(default_factory=dict)
    per_ep_err: dict[str, int] = field(default_factory=dict)

    def add(self, ep: str, ms: float, err: str | None, nbytes: int = 0) -> None:
        self.lat.append(ms)
        self.per_ep.setdefault(ep, []).append(ms)
        if err:
            self.errors[err] = self.errors.get(err, 0) + 1
            self.per_ep_err[ep] = self.per_ep_err.get(ep, 0) + 1
        else:
            self.ok += 1
            self.bytes += nbytes

    @property
    def total(self) -> int:
        return len(self.lat)

    @property
    def err_count(self) -> int:
        return sum(self.errors.values())

    @property
    def err_rate(self) -> float:
        return self.err_count / self.total if self.total else 0.0

    def pct(self, p: float) -> float:
        return percentile(self.lat, p)

    def summary(self) -> dict:
        slow = sorted(((percentile(v, 95), k) for k, v in self.per_ep.items()), reverse=True)[:3]
        return {
            "users": self.users, "duration_s": round(self.duration, 1), "requests": self.total,
            "rps": round(self.total / self.duration, 1) if self.duration else 0,
            "throughput_kib_s": round(self.bytes / 1024 / self.duration, 1) if self.duration else 0,
            "p50_ms": round(self.pct(50), 1), "p90_ms": round(self.pct(90), 1), "p95_ms": round(self.pct(95), 1),
            "p99_ms": round(self.pct(99), 1), "max_ms": round(max(self.lat), 1) if self.lat else 0,
            "error_rate": round(self.err_rate, 5), "errors": dict(self.errors),
            "slowest_endpoints_p95": [{"endpoint": k, "p95_ms": round(v, 1)} for v, k in slow],
            "endpoint_errors": dict(self.per_ep_err),
        }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class Thresholds:
    comfort_p95: float = 300.0
    comfort_err: float = 0.001
    normal_p95: float = 1000.0
    normal_err: float = 0.01
    stop_p95: float = 2000.0
    stop_err: float = 0.05


def classify(p95: float, err_rate: float, t: Thresholds) -> str:
    """Зона ступени: comfort / normal / overload."""
    if p95 <= t.comfort_p95 and err_rate <= t.comfort_err:
        return "comfort"
    if p95 <= t.normal_p95 and err_rate < t.normal_err:
        return "normal"
    return "overload"


def should_stop(p95: float, err_rate: float, t: Thresholds) -> bool:
    return p95 > t.stop_p95 or err_rate > t.stop_err


ZONE_RU = {"comfort": "КОМФОРТ", "normal": "НОРМА", "overload": "ПЕРЕБОР"}


# --------------------------------------------------------------------------- модель аудитории
@dataclass
class Audience:
    session_min: float = 5.0        # средняя длина визита, мин
    sessions_per_day: float = 2.0   # визитов на одного активного пользователя в день
    peak_hour_share: float = 0.25   # доля дневных визитов, приходящаяся на пиковый час

    def estimate(self, concurrent: int) -> dict:
        """Закон Литтла: одновременные = поток визитов/мин × длина визита."""
        if concurrent <= 0:
            return {"peak_hour_users": 0, "daily_users": 0}
        visits_per_hour = concurrent * 60.0 / self.session_min
        daily_visits = visits_per_hour / self.peak_hour_share
        return {"peak_hour_users": int(visits_per_hour), "daily_users": int(daily_visits / self.sessions_per_day)}

    def text(self) -> str:
        return (f"визит ≈ {self.session_min:g} мин, {self.sessions_per_day:g} визита/день на человека, "
                f"на пиковый час приходится {self.peak_hour_share:.0%} дневных визитов. "
                f"Одновременные × 60/{self.session_min:g} = визитов в пиковый час; "
                f"÷ {self.peak_hour_share:g} = визитов в день; ÷ {self.sessions_per_day:g} = людей в день")


# --------------------------------------------------------------------------- нагрузка
class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.a = args
        self.base = args.url.rstrip("/")
        self.headers = {"User-Agent": "KipClub-stress/1.0 (guest, read-only)", "Accept-Encoding": "gzip"}
        if args.host_header:
            self.headers["Host"] = args.host_header
        self.club_ids: list[int] = []
        self.inflight = 0
        self.step: StepStats | None = None
        self.stop = asyncio.Event()
        self.timeout = aiohttp.ClientTimeout(total=args.timeout)

    async def fetch(self, s: aiohttp.ClientSession, path: str, label: str | None = None) -> None:
        label = label or endpoint_label(path)
        t0 = time.perf_counter()
        err, n = None, 0
        self.inflight += 1
        try:
            async with s.get(self.base + path, headers=self.headers, allow_redirects=True) as r:
                body = await r.read()
                n = len(body)
                if r.status == 429:
                    err = "429"
                elif r.status >= 500:
                    err = "5xx"
                elif r.status >= 400:
                    err = f"{r.status}"
        except asyncio.TimeoutError:
            err = "timeout"
        except aiohttp.ClientConnectionError:
            err = "connection"
        except aiohttp.ClientError:
            err = "client"
        self.inflight -= 1
        ms = (time.perf_counter() - t0) * 1000
        st = self.step
        if st is not None and not self.stop.is_set():
            st.add(label, ms, err, n)

    def pick(self) -> tuple[str, str]:
        _, name, path = random.choices(ACTIONS, weights=[w for w, _, _ in ACTIONS])[0]
        if "{club}" in path:
            if not self.club_ids:
                return "api_clubs", "/api/clubs"
            path = path.replace("{club}", str(random.choice(self.club_ids)))
        path = path.replace("{weekday}", str(random.randint(1, 6)))
        if "{week}" in path:  # как фронт: понедельник текущей недели, иногда соседние недели
            today = datetime.date.today()
            monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=random.choice([0, 0, 0, 1, -1]))
            path = path.replace("{week}", monday.isoformat())
        return name, path

    async def user(self, s: aiohttp.ClientSession, my_stop: asyncio.Event) -> None:
        await asyncio.sleep(random.uniform(0, self.a.think_max))  # не стартуем все в одну миллисекунду
        while not my_stop.is_set() and not self.stop.is_set():
            _, path = self.pick()
            await self.fetch(s, path, "/api/clubs/{id}" if path.startswith("/api/clubs/") else None)
            base = endpoint_label(path)
            if base in PAGE_ASSETS and random.random() < STATIC_SAMPLE:
                await asyncio.gather(*(self.fetch(s, p, "static css/js") for p in PAGE_ASSETS[base]))
            try:
                await asyncio.wait_for(my_stop.wait(), random.uniform(self.a.think_min, self.a.think_max))
            except asyncio.TimeoutError:
                pass

    async def preflight(self, s: aiohttp.ClientSession) -> bool:
        for path in ("/readyz", "/api/health"):
            try:
                async with s.get(self.base + path, headers=self.headers) as r:
                    if r.status != 200:
                        print(f"✖ {path} → HTTP {r.status}. Сервер не готов — тест не запускаю.")
                        return False
            except Exception as exc:  # noqa: BLE001
                print(f"✖ {self.base}{path} недоступен: {type(exc).__name__}: {exc}. Тест не запускаю.")
                return False
        try:
            async with s.get(self.base + "/api/clubs", headers=self.headers) as r:
                self.club_ids = [c["id"] for c in await r.json() if isinstance(c, dict) and "id" in c][:200]
        except Exception:  # noqa: BLE001
            self.club_ids = []
        print(f"✔ Сервер жив ({self.base}), кружков в базе: {len(self.club_ids)}")
        return True

    async def run(self) -> list[dict]:
        t = self.a.thresholds
        results: list[dict] = []
        conn = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=conn, timeout=self.timeout) as s:
            if not await self.preflight(s):
                return []
            t_start = time.monotonic()
            tasks: list[asyncio.Task] = []
            user_stop = asyncio.Event()
            for users in self.a.steps:
                if self.stop.is_set():
                    break
                if users > self.a.max_users:
                    print(f"· Достигнут лимит --max-users={self.a.max_users}, дальше не растём.")
                    break
                left = self.a.max_duration - (time.monotonic() - t_start)
                if left < self.a.step_duration * 0.5:
                    print(f"· Достигнут лимит общего времени --max-duration={self.a.max_duration:g} c.")
                    self.a.stop_reason = "лимит времени"
                    break
                dur = min(self.a.step_duration, left)
                self.step = st = StepStats(users=users)
                while len(tasks) < users:  # пользователи накапливаются: 5 → 10 → 25 …
                    tasks.append(asyncio.create_task(self.user(s, user_stop)))
                print(f"→ ступень {users:>5} одновременных, {dur:.0f} c …", end="", flush=True)
                await asyncio.sleep(min(self.a.think_max, dur / 4))  # прогрев: в статистику не идёт
                st = self.step = StepStats(users=users)
                st.started = time.monotonic()
                try:
                    await asyncio.wait_for(self.stop.wait(), dur)
                except asyncio.TimeoutError:
                    pass
                st.duration = time.monotonic() - st.started
                self.step = None
                # запросы, которые висят дольше половины ступени и не успели закончиться, — это тоже отказы
                stalled = self.inflight if (st.total < self.inflight or st.total == 0) else 0
                if stalled:
                    st.errors["hang"] = stalled
                    st.lat.extend([dur * 1000] * stalled)
                sm = st.summary()
                sm["zone"] = classify(st.pct(95), st.err_rate, t)
                results.append(sm)
                print(f"  rps={sm['rps']:<7} p95={sm['p95_ms']:>7.0f} мс  ошибки={sm['error_rate']:.2%}  → {ZONE_RU[sm['zone']]}")
                if self.stop.is_set():
                    self.a.stop_reason = "Ctrl+C"
                    break
                if should_stop(st.pct(95), st.err_rate, t):
                    self.a.stop_reason = (f"перегрузка: p95 {st.pct(95):.0f} мс > {t.stop_p95:g} мс"
                                          if st.pct(95) > t.stop_p95 else
                                          f"перегрузка: ошибок {st.err_rate:.1%} > {t.stop_err:.0%}")
                    print(f"■ Авто-стоп — {self.a.stop_reason}")
                    break
            else:
                self.a.stop_reason = self.a.stop_reason or "пройдены все ступени"
            user_stop.set()
            for tk in tasks:
                tk.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(3)
            try:  # жив ли сервер после теста (обрыв без восстановления = зависание, а не просто медленность)
                async with s.get(self.base + "/healthz", headers=self.headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    self.a.alive_after = r.status == 200
            except Exception:  # noqa: BLE001
                self.a.alive_after = False
        return results


# --------------------------------------------------------------------------- отчёт
def build_report(results: list[dict], args: argparse.Namespace) -> tuple[str, dict]:
    t: Thresholds = args.thresholds
    aud: Audience = args.audience
    best = {z: 0 for z in ("comfort", "normal")}
    first_over = None
    for r in results:
        z = r["zone"]
        if first_over is None:
            if z == "comfort":
                best["comfort"] = r["users"]
                best["normal"] = r["users"]
            elif z == "normal":
                best["normal"] = r["users"]
            else:
                first_over = r
    L: list[str] = []
    L.append("# Отчёт стресс-теста KipClub")
    L.append(f"Цель: {args.url}" + (f" (Host: {args.host_header})" if args.host_header else ""))
    L.append(f"Причина остановки: {args.stop_reason or '—'}")
    L.append(f"Пауза между действиями пользователя: {args.think_min:g}–{args.think_max:g} c; ступень {args.step_duration:g} c; "
             f"таймаут запроса {args.timeout:g} c")
    L.append(f"Пороги: комфорт p95 ≤ {t.comfort_p95:g} мс и ошибок ≤ {t.comfort_err:.1%}; норма p95 ≤ {t.normal_p95:g} мс и "
             f"ошибок < {t.normal_err:.0%}; авто-стоп p95 > {t.stop_p95:g} мс или ошибок > {t.stop_err:.0%}")
    L.append("")
    L.append("| Польз. | Запросов | RPS | КиБ/с | p50 | p90 | p95 | p99 | max | Ошибки | Таймаут | 5xx | 429 | Соедин. | Зона |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        e = r["errors"]
        L.append(f"| {r['users']} | {r['requests']} | {r['rps']} | {r['throughput_kib_s']} | {r['p50_ms']:.0f} | {r['p90_ms']:.0f} | "
                 f"{r['p95_ms']:.0f} | {r['p99_ms']:.0f} | {r['max_ms']:.0f} | {r['error_rate']:.2%} | {e.get('timeout', 0) + e.get('hang', 0)} | "
                 f"{e.get('5xx', 0)} | {e.get('429', 0)} | {e.get('connection', 0) + e.get('client', 0)} | {ZONE_RU[r['zone']]} |")
    L.append("")
    L.append("## Итог (оценка)")

    def fmt(n: int) -> str:
        est = aud.estimate(n)
        return f"{n} одновременных (~{est['peak_hour_users']} человек за пиковый час, ~{est['daily_users']} пользователей в день)"

    L.append(f"- 🟢 Комфортно до {fmt(best['comfort'])}" if best["comfort"] else "- 🟢 Комфортной зоны не достигнуто даже на первой ступени")
    L.append(f"- 🟡 Нормально до {fmt(best['normal'])}" if best["normal"] else "- 🟡 Нормальной зоны не достигнуто")
    if first_over:
        L.append(f"- 🔴 Перебор с {fmt(first_over['users'])}")
    else:
        top = results[-1]["users"] if results else 0
        L.append(f"- 🔴 Перебор не достигнут: сервер держал все {top} одновременных. Реальный предел выше — "
                 f"увеличь --steps/--max-users (или клиентская машина стала узким местом).")
    L.append("")
    L.append(f"Модель аудитории (это ОЦЕНКА, не измерение): {aud.text()}. "
             "«Одновременный» = человек с открытым сайтом/приложением, который каждые "
             f"{args.think_min:g}–{args.think_max:g} c что-то делает; реальные люди обычно медленнее, так что запас есть.")
    L.append("")
    L.append("## Узкие места")
    focus = first_over or (results[-1] if results else None)
    if focus:
        sl = ", ".join(f"{x['endpoint']} p95={x['p95_ms']:.0f} мс" for x in focus["slowest_endpoints_p95"])
        L.append(f"- Самые медленные на ступени {focus['users']}: {sl}")
    first_err = next((r for r in results if r["endpoint_errors"]), None)
    if first_err:
        ep = sorted(first_err["endpoint_errors"].items(), key=lambda x: -x[1])
        L.append(f"- Первые ошибки на ступени {first_err['users']}: " + ", ".join(f"{k} ×{v}" for k, v in ep[:5])
                 + f"; типы: {first_err['errors']}")
    else:
        L.append("- Ошибок не было.")
    prev = results[results.index(first_over) - 1] if first_over and results.index(first_over) > 0 else None
    if first_over and prev and prev["zone"] == "comfort" and (first_over["errors"].get("timeout", 0) + first_over["errors"].get("hang", 0)) > 0.5 * first_over["requests"]:
        L.append(f"- ⚠ Резкий обрыв: на {prev['users']} всё было комфортно (p95 {prev['p95_ms']:.0f} мс), а на "
                 f"{first_over['users']} почти все запросы — таймауты. Так выглядит не плавная деградация, а исчерпание "
                 "пула потоков/соединений к БД (зависание), а не нехватка CPU.")
    if getattr(args, "alive_after", True) is False:
        L.append("- 🛑 После теста /healthz НЕ отвечает за 5 c — сервер завис и сам не восстановился. Нужен перезапуск.")
    elif hasattr(args, "alive_after"):
        L.append("- После теста /healthz отвечает — сервер восстановился.")
    total429 = sum(r["errors"].get("429", 0) for r in results)
    if total429:
        L.append(f"- ⚠ Получено {total429} ответов 429 (лимит частоты). Весь тест идёт с ОДНОГО IP, поэтому лимитер "
                 "может срезать результат раньше, чем кончится мощность сервера: 429 — это не падение, а защита.")
    else:
        L.append("- 429 не было. (В backend нет общего лимитера на публичные GET — лимиты только на вход, push-подписки, "
                 "/api/logs и /api/app/devices, которые тест не трогает.)")
    L.append("- Нагрузка идёт с одной машины: при сотнях пользователей узким местом может стать сам клиент (CPU, сеть, "
             "Wi-Fi). Если p95 растёт, а CPU сервера низкий — проверь клиента. Прод: uvicorn --workers 1 + SQLite, "
             "т.е. одно ядро Python; это главный потолок.")
    text = "\n".join(L)
    data = {"target": args.url, "host_header": args.host_header, "stop_reason": args.stop_reason,
            "thresholds": t.__dict__, "audience_model": aud.__dict__, "steps": results,
            "verdict": {"comfort_max_concurrent": best["comfort"], "normal_max_concurrent": best["normal"],
                        "overload_from_concurrent": first_over["users"] if first_over else None,
                        "comfort_estimate": aud.estimate(best["comfort"]), "normal_estimate": aud.estimate(best["normal"])}}
    return text, data


# --------------------------------------------------------------------------- CLI
def is_local(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local") or host.startswith(("192.168.", "10."))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Стресс-тест KipClub (гости, только чтение) с авто-остановкой и отчётом")
    p.add_argument("--url", default="http://127.0.0.1:8000", help="адрес сервера (по умолчанию локальный dev)")
    p.add_argument("--host-header", default="", help="заголовок Host (прод: lekora.ru:7443)")
    p.add_argument("--yes-prod", action="store_true", help="подтверждаю запуск против НЕлокального сервера")
    p.add_argument("--steps", default="5,10,25,50,100,200,400,800,1200,1600",
                   help="ступени одновременных пользователей через запятую")
    p.add_argument("--step-duration", type=float, default=30, help="длительность ступени, c")
    p.add_argument("--max-users", type=int, default=2000, help="не поднимать выше этого числа пользователей")
    p.add_argument("--max-duration", type=float, default=600, help="жёсткий лимит общего времени теста, c")
    p.add_argument("--think-min", type=float, default=2.0, help="мин. пауза между действиями, c")
    p.add_argument("--think-max", type=float, default=5.0, help="макс. пауза между действиями, c")
    p.add_argument("--timeout", type=float, default=10.0, help="таймаут одного запроса, c")
    p.add_argument("--comfort-p95", type=float, default=300)
    p.add_argument("--comfort-err", type=float, default=0.001, help="доля, 0.001 = 0.1%%")
    p.add_argument("--normal-p95", type=float, default=1000)
    p.add_argument("--normal-err", type=float, default=0.01)
    p.add_argument("--stop-p95", type=float, default=2000, help="авто-стоп, если p95 ступени выше, мс")
    p.add_argument("--stop-err", type=float, default=0.05, help="авто-стоп, если доля ошибок выше")
    p.add_argument("--session-min", type=float, default=5.0, help="модель: средний визит, мин")
    p.add_argument("--sessions-per-day", type=float, default=2.0, help="модель: визитов на человека в день")
    p.add_argument("--peak-share", type=float, default=0.25, help="модель: доля дневных визитов в пиковый час")
    p.add_argument("--out", default="stress-report", help="префикс файлов отчёта (.json и .md)")
    p.add_argument("--seed", type=int, default=None)
    a = p.parse_args(argv)
    a.steps = sorted({int(x) for x in a.steps.split(",") if x.strip()})
    a.thresholds = Thresholds(a.comfort_p95, a.comfort_err, a.normal_p95, a.normal_err, a.stop_p95, a.stop_err)
    a.audience = Audience(a.session_min, a.sessions_per_day, a.peak_share)
    a.stop_reason = ""
    if a.think_max < a.think_min:
        p.error("--think-max меньше --think-min")
    return a


def main(argv: list[str] | None = None) -> int:
    if aiohttp is None:
        print("Нужен aiohttp:  pip install aiohttp")
        return 2
    a = parse_args(argv)
    if a.seed is not None:
        random.seed(a.seed)
    if not is_local(a.url):
        print("⚠ ВНИМАНИЕ: цель НЕ локальная —", a.url)
        print("  Тест создаёт реальную нагрузку и может замедлить сайт для живых пользователей.")
        if not a.yes_prod:
            print("  Для запуска добавь флаг --yes-prod (лучше в тихое время).")
            return 3
    runner = Runner(a)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.add_signal_handler(signal.SIGINT, runner.stop.set)
    except (NotImplementedError, RuntimeError):  # Windows: обработаем KeyboardInterrupt ниже
        signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(runner.stop.set))
    t0 = time.monotonic()
    try:
        results = loop.run_until_complete(runner.run())
    finally:
        loop.close()
    if not results:
        return 1
    text, data = build_report(results, a)
    data["total_seconds"] = round(time.monotonic() - t0, 1)
    print("\n" + text)
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(text + "\n", encoding="utf-8")
    print(f"\nОтчёт сохранён: {out.with_suffix('.md')} и {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    sys.exit(main())
