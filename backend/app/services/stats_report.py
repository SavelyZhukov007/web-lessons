"""Вкладка «Статистика» в админке: восемь блоков и CSV по каждому. Только агрегаты, без текстов и идентификаторов."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Broadcast, BroadcastReceipt, Club
from ..models.usage import ClientErrorCount, InstallActivity, PerfDaily, RetentionWeekly, UsageDaily, VersionDaily
from .clock import today_msk
from .usage import active_on, day_retention

PLATFORMS = ("web", "pwa", "ios", "android")
BLOCKS = ("users", "retention", "versions", "funnels", "usage", "push", "quality", "feedback")
FUNNELS = {
    "pwa": ("install_banner", "install_prompt", "install_accept", "installed", "standalone_open"),
    "ios": ("ios_guide_open", "ios_guide_step", "ios_first_standalone"),
    "apk": ("apk_page", "apk_download", "apk_first_run"),
}
BUCKET_LABELS = {"b1": "<1 с", "b2": "1..2,5 с", "b3": "2,5..4 с", "b4": ">4 с"}
CLS_LABELS = {"b1": "хорошо", "b2": "терпимо", "b3": "плохо", "b4": "плохо"}


def _counts(db: Session, since: date, metrics: tuple[str, ...] | None = None, by=("metric", "dim")) -> list:
    cols = [getattr(UsageDaily, c) for c in by]
    q = select(*cols, func.sum(UsageDaily.count)).where(UsageDaily.day >= since, UsageDaily.platform != "server")
    if metrics:
        q = q.where(UsageDaily.metric.in_(metrics))
    return db.execute(q.group_by(*cols)).all()


def _metric_total(db: Session, since: date, metric: str, platform: str | None = None) -> int:
    q = select(func.sum(UsageDaily.count)).where(UsageDaily.day >= since, UsageDaily.metric == metric)
    if platform:
        q = q.where(UsageDaily.platform == platform)
    return int(db.scalar(q) or 0)


def users(db: Session, today: date, days: int) -> dict:
    span = days + 30
    rows = db.scalars(select(InstallActivity).where(InstallActivity.last_day >= today - timedelta(days=span))).all()
    # active[k]: был ли запуск k дней назад; один проход по битовой маске на установку
    marks = [(r.platform, [active_on(r, today - timedelta(days=k)) for k in range(span)]) for r in rows]
    series = []
    for i in range(days - 1, -1, -1):
        point = {"day": str(today - timedelta(days=i))}
        for name, window in (("dau", 1), ("wau", 7), ("mau", 30)):
            per = defaultdict(int)
            for platform, active in marks:
                if any(active[i:i + window]):
                    per[platform] += 1
            point[name] = sum(per.values())
            if name == "dau":
                point["by_platform"] = {p: per.get(p, 0) for p in PLATFORMS}
        series.append(point)
    last = series[-1] if series else {"dau": 0, "wau": 0, "mau": 0}
    week = series[-7:]
    avg_dau = sum(p["dau"] for p in week) / len(week) if week else 0
    return {"series": series, "today": last, "stickiness": round(avg_dau / last["mau"], 3) if last.get("mau") else None,
            "installs_tracked": len(rows)}


def retention(db: Session, today: date) -> dict:
    cohorts = defaultdict(lambda: {"size": 0, "weeks": defaultdict(int)})
    for r in db.scalars(select(RetentionWeekly).where(RetentionWeekly.cohort_week >= today - timedelta(weeks=16))):
        c = cohorts[str(r.cohort_week)]
        if r.week_n == 0:
            c["size"] += r.size
        c["weeks"][r.week_n] += r.active
    table = [{"cohort_week": k, "size": v["size"], "weeks": [v["weeks"].get(n, 0) for n in range(max(v["weeks"], default=0) + 1)]}
             for k, v in sorted(cohorts.items())]
    rows = db.scalars(select(InstallActivity)).all()
    return {"cohorts": table, "days": day_retention(rows, today),
            "by_platform": {p: day_retention([r for r in rows if r.platform == p], today) for p in PLATFORMS}}


def versions(db: Session, since: date) -> dict:
    rows = db.execute(select(VersionDaily.day, VersionDaily.platform, VersionDaily.version, VersionDaily.active)
                      .where(VersionDaily.day >= since).order_by(VersionDaily.day)).all()
    by_day = defaultdict(lambda: defaultdict(int))
    for d, _p, v, n in rows:
        by_day[str(d)][v] += n
    all_versions = sorted({v for _d, _p, v, _n in rows}, key=lambda v: tuple(int(x) for x in v.split(".")))
    latest = all_versions[-1] if all_versions else ""
    last_day = max(by_day) if by_day else None
    on_latest = by_day[last_day].get(latest, 0) if last_day else 0
    total_last = sum(by_day[last_day].values()) if last_day else 0
    return {"versions": all_versions, "latest": latest,
            "series": [{"day": d, "counts": dict(v)} for d, v in sorted(by_day.items())],
            "on_old": total_last - on_latest, "on_old_share": round((total_last - on_latest) / total_last, 3) if total_last else None}


def funnels(db: Session, since: date) -> dict:
    out = {}
    for name, steps in FUNNELS.items():
        out[name] = [{"metric": m, "count": _metric_total(db, since, m)} for m in steps]
    out["apk"].insert(2, {"metric": "apk_download_server", "count": _metric_total(db, since, "apk_download", "server")})
    out["apk"][1]["count"] -= out["apk"][2]["count"]  # клики в приложении отдельно от отдачи файла сервером
    return out


def usage(db: Session, since: date) -> dict:
    groups = defaultdict(list)
    wanted = ("screen_view", "schedule_view", "schedule_nav", "search_open", "search_results", "search_pick", "search_abandon",
              "filter_apply", "calendar_export", "calendar_fail", "tour_open", "share", "print", "offline_open", "offline_view_stale",
              "fav_add", "fav_remove", "app_open", "app_resume", "load_source")
    for metric, dim, n in _counts(db, since, wanted):
        groups[metric].append({"dim": dim, "count": int(n)})
    for v in groups.values():
        v.sort(key=lambda x: -x["count"])
    weekdays = [0] * 7
    for d, n in db.execute(select(UsageDaily.day, func.sum(UsageDaily.count)).where(
            UsageDaily.day >= since, UsageDaily.metric.in_(("screen_view", "schedule_view"))).group_by(UsageDaily.day)):
        weekdays[d.weekday()] += int(n)
    clubs = defaultdict(int)
    for _m, dim, n in _counts(db, since, ("club_view",)):
        if dim.startswith("c") and dim[1:].isdigit():
            clubs[int(dim[1:])] += int(n)
    names = dict(db.execute(select(Club.id, Club.name).where(Club.id.in_(list(clubs) or [0]))).all())
    top = sorted(({"club_id": k, "name": names.get(k, f"#{k}"), "count": n} for k, n in clubs.items()), key=lambda x: -x["count"])[:10]
    return {"events": dict(groups), "weekdays": weekdays, "top_clubs": top}


def push(db: Session, since: date) -> dict:
    sent = db.execute(select(func.sum(func.max(Broadcast.web_sent, 0)), func.sum(func.max(Broadcast.web_failed, 0)),
                             func.sum(func.max(Broadcast.fcm_sent, 0)), func.sum(func.max(Broadcast.fcm_failed, 0)))
                      .where(Broadcast.created_at >= since)).one()
    receipts = defaultdict(lambda: {"shown": 0, "opened": 0})
    for channel, shown, opened in db.execute(select(BroadcastReceipt.channel, func.count(), func.count(BroadcastReceipt.opened_at))
                                             .where(BroadcastReceipt.shown_at >= since).group_by(BroadcastReceipt.channel)):
        receipts[channel] = {"shown": shown, "opened": opened}
    channels = {
        "web": {"sent": int(sent[0] or 0), "failed": int(sent[1] or 0), **receipts.get("web", {"shown": 0, "opened": 0})},
        "ios": {"sent": None, "failed": None, **receipts.get("ios", {"shown": 0, "opened": 0})},
        "fcm": {"sent": int(sent[2] or 0), "failed": int(sent[3] or 0), **receipts.get("android", {"shown": 0, "opened": 0})},
    }
    client = defaultdict(dict)
    for metric, dim, n in _counts(db, since, ("push_shown", "push_open", "push_dismiss", "push_permission", "push_subscribe", "push_unsubscribe")):
        client[metric][dim] = int(n)
    recent = []
    for b in db.scalars(select(Broadcast).where(Broadcast.created_at >= since).order_by(Broadcast.id.desc()).limit(20)):
        per = {c: {"shown": s, "opened": o} for c, s, o in db.execute(
            select(BroadcastReceipt.channel, func.count(), func.count(BroadcastReceipt.opened_at))
            .where(BroadcastReceipt.broadcast_id == b.id).group_by(BroadcastReceipt.channel))}
        recent.append({"id": b.id, "title": (b.title or "")[:80], "created_at": str(b.created_at)[:16],
                       "web_sent": max(b.web_sent or 0, 0), "fcm_sent": max(b.fcm_sent or 0, 0), "receipts": per})
    return {"channels": channels, "client": dict(client), "broadcasts": recent}


def _p_bucket(counts: dict[str, int], q: float) -> str | None:
    total = sum(counts.values())
    if not total:
        return None
    acc = 0
    for b in ("b1", "b2", "b3", "b4"):
        acc += counts.get(b, 0)
        if acc >= q * total:
            return b
    return "b4"


def _is_version(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def quality(db: Session, since: date) -> dict:
    errors = db.execute(select(ClientErrorCount.build, ClientErrorCount.platform, ClientErrorCount.code, ClientErrorCount.source,
                               ClientErrorCount.line, func.sum(ClientErrorCount.count), func.min(ClientErrorCount.day))
                        .where(ClientErrorCount.day >= since)
                        .group_by(ClientErrorCount.build, ClientErrorCount.platform, ClientErrorCount.code, ClientErrorCount.source,
                                  ClientErrorCount.line)).all()
    by_version = defaultdict(int)
    seen_in: dict[tuple, set] = defaultdict(set)
    for build, _p, code, source, line, n, _first in errors:
        by_version[build] += int(n)
        seen_in[(code, source, line)].add(build)
    versions_sorted = sorted((b for b in by_version if _is_version(b)), key=lambda v: tuple(int(x) for x in v.split(".")))
    latest = versions_sorted[-1] if versions_sorted else None
    new_after = [{"code": c, "source": s, "line": ln, "count": int(n)} for b, _p, c, s, ln, n, _f in errors
                 if latest and b == latest and seen_in[(c, s, ln)] == {latest}]
    top = sorted(({"version": b, "platform": p, "code": c, "source": s, "line": ln, "count": int(n)} for b, p, c, s, ln, n, _f in errors),
                 key=lambda x: -x["count"])[:20]
    api = [{"dim": d, "count": int(n)} for _m, d, n in _counts(db, since, ("api_error",))]
    crashes = [{"dim": d, "count": int(n)} for _m, d, n in _counts(db, since, ("native_crash",))]
    perf = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for p, m, b, n in db.execute(select(PerfDaily.platform, PerfDaily.metric, PerfDaily.bucket, func.sum(PerfDaily.count))
                                 .where(PerfDaily.day >= since).group_by(PerfDaily.platform, PerfDaily.metric, PerfDaily.bucket)):
        perf[p][m][b] += int(n)
    perf_out = [{"platform": p, "metric": m, "p50": _p_bucket(c, .5), "p75": _p_bucket(c, .75), "samples": sum(c.values()), "buckets": dict(c)}
                for p, ms in perf.items() for m, c in ms.items()]
    return {"errors_by_version": dict(by_version), "latest": latest, "new_after_release": new_after, "top_errors": top,
            "api_errors": sorted(api, key=lambda x: -x["count"]), "native_crashes": crashes, "perf": perf_out,
            "bucket_labels": BUCKET_LABELS, "cls_labels": CLS_LABELS}


def feedback(db: Session, since: date) -> dict:
    ratings = defaultdict(lambda: {"sum": 0, "count": 0, "dist": {str(i): 0 for i in range(1, 6)}})
    for platform, version, dim, n in db.execute(
            select(UsageDaily.platform, UsageDaily.version, UsageDaily.dim, func.sum(UsageDaily.count))
            .where(UsageDaily.day >= since, UsageDaily.metric == "fb_rating").group_by(UsageDaily.platform, UsageDaily.version, UsageDaily.dim)):
        if dim in ("1", "2", "3", "4", "5"):
            for key in (f"v:{version or '?'}", f"p:{platform}", "all"):
                r = ratings[key]
                r["sum"] += int(dim) * int(n)
                r["count"] += int(n)
                r["dist"][dim] += int(n)
    avg = {k: {"avg": round(v["sum"] / v["count"], 2) if v["count"] else None, "count": v["count"], "dist": v["dist"]} for k, v in ratings.items()}
    prompts = defaultdict(dict)
    for metric, dim, n in _counts(db, since, ("fb_prompt_shown", "fb_prompt_dismiss", "fb_prompt_snooze", "fb_form_open", "fb_sent")):
        prompts[metric][dim] = int(n)
    return {"overall": avg.get("all", {"avg": None, "count": 0}),
            "by_version": {k[2:]: v for k, v in avg.items() if k.startswith("v:")},
            "by_platform": {k[2:]: v for k, v in avg.items() if k.startswith("p:")}, "prompts": dict(prompts)}


def report(db: Session, days: int = 90, today: date | None = None) -> dict:
    today = today or today_msk()
    days = max(7, min(days, 90))
    since = today - timedelta(days=days - 1)
    return {"days": days, "since": str(since), "today": str(today),
            "users": users(db, today, days), "retention": retention(db, today), "versions": versions(db, since),
            "funnels": funnels(db, since), "usage": usage(db, since), "push": push(db, since),
            "quality": quality(db, since), "feedback": feedback(db, since)}


def csv_rows(block: str, data: dict) -> list[list]:
    """Плоская таблица для CSV одного блока."""
    if block == "users":
        return [["day", "dau", "wau", "mau", *PLATFORMS]] + [
            [p["day"], p["dau"], p["wau"], p["mau"], *(p["by_platform"][x] for x in PLATFORMS)] for p in data["series"]]
    if block == "retention":
        width = max((len(c["weeks"]) for c in data["cohorts"]), default=1)
        rows = [["cohort_week", "size", *(f"week_{n}" for n in range(width))]]
        rows += [[c["cohort_week"], c["size"], *c["weeks"]] for c in data["cohorts"]]
        rows += [[], ["metric", "cohort", "kept", "rate"]] + [[k, v["cohort"], v["kept"], v["rate"]] for k, v in data["days"].items()]
        return rows
    if block == "versions":
        return [["day", *data["versions"]]] + [[s["day"], *(s["counts"].get(v, 0) for v in data["versions"])] for s in data["series"]]
    if block == "funnels":
        return [["funnel", "step", "count"]] + [[f, s["metric"], s["count"]] for f, steps in data.items() for s in steps]
    if block == "usage":
        rows = [["metric", "dim", "count"]] + [[m, e["dim"], e["count"]] for m, items in data["events"].items() for e in items]
        rows += [[], ["weekday", "count"]] + [[i + 1, n] for i, n in enumerate(data["weekdays"])]
        rows += [[], ["club_id", "club", "views"]] + [[c["club_id"], c["name"], c["count"]] for c in data["top_clubs"]]
        return rows
    if block == "push":
        rows = [["channel", "sent", "failed", "shown", "opened"]] + [[c, v["sent"], v["failed"], v["shown"], v["opened"]] for c, v in data["channels"].items()]
        rows += [[], ["client_metric", "dim", "count"]] + [[m, d, n] for m, dims in data["client"].items() for d, n in dims.items()]
        rows += [[], ["broadcast_id", "created_at", "web_sent", "fcm_sent", "receipts"]] + [
            [b["id"], b["created_at"], b["web_sent"], b["fcm_sent"], "; ".join(f"{c}: {r['shown']}/{r['opened']}" for c, r in b["receipts"].items())]
            for b in data["broadcasts"]]
        return rows
    if block == "quality":
        rows = [["version", "errors"]] + [[v, n] for v, n in data["errors_by_version"].items()]
        rows += [[], ["version", "platform", "code", "source", "line", "count"]] + [
            [e["version"], e["platform"], e["code"], e["source"], e["line"], e["count"]] for e in data["top_errors"]]
        rows += [[], ["api_error", "count"]] + [[e["dim"], e["count"]] for e in data["api_errors"]]
        rows += [[], ["native_crash", "count"]] + [[e["dim"], e["count"]] for e in data["native_crashes"]]
        rows += [[], ["platform", "metric", "p50", "p75", "samples"]] + [[p["platform"], p["metric"], p["p50"], p["p75"], p["samples"]] for p in data["perf"]]
        return rows
    if block == "feedback":
        rows = [["scope", "key", "avg", "count", "r1", "r2", "r3", "r4", "r5"]]
        for scope in ("by_version", "by_platform"):
            rows += [[scope, k, v["avg"], v["count"], *(v["dist"][str(i)] for i in range(1, 6))] for k, v in data[scope].items()]
        rows += [[], ["prompt_metric", "source", "count"]] + [[m, d, n] for m, dims in data["prompts"].items() for d, n in dims.items()]
        return rows
    raise KeyError(block)


def to_csv(block: str, data: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    for row in csv_rows(block, data):
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()  # BOM: Excel открывает кириллицу без настройки
