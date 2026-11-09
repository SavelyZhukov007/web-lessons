"""Opt-in, anonymous counters; retry dedup is a random batch, never a person identifier."""

from collections import Counter
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models.usage import ClientErrorCount, UsageBatch, UsageCounter
from .clock import today_msk

Metric = Literal[
    "page_open",
    "install_banner",
    "install_open",
    "install_download",
    "install_prompt_available",
    "install_prompt",
    "install_accept",
    "install_decline",
    "installed",
    "standalone_open",
    "search_open",
    "search_results",
    "search_pick",
    "search_abandon",
]
Bucket = Literal["none", "one", "few", "many", "home", "club", "clubs", "install", "other"]
Platform = Literal["web", "pwa", "ios", "android"]


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Metric
    bucket: Bucket = "none"


class ErrorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "URIError", "EvalError", "ResourceError", "UnhandledRejection"
    ]
    source: str = Field(default="unknown", max_length=100, pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    line: int = Field(default=0, ge=0, le=1000000)


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]{32}$")
    platform: Platform
    build: str = Field(default="local", max_length=64, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    events: list[EventIn] = Field(default_factory=list, max_length=20)
    errors: list[ErrorIn] = Field(default_factory=list, max_length=20)


def record(db: Session, body: BatchIn):
    day = today_msk()
    if not body.events and not body.errors:
        return {"accepted": 0, "duplicate": False}
    claimed = db.execute(insert(UsageBatch).values(id=body.batch_id, day=day).on_conflict_do_nothing()).rowcount
    if not claimed:
        db.rollback()
        return {"accepted": 0, "duplicate": True}
    for (metric, bucket), count in Counter((e.metric, e.bucket) for e in body.events).items():
        stmt = insert(UsageCounter).values(day=day, platform=body.platform, metric=metric, bucket=bucket, count=count)
        db.execute(
            stmt.on_conflict_do_update(index_elements=["day", "platform", "metric", "bucket"], set_={"count": UsageCounter.count + count})
        )
    for (code, source, line), count in Counter((e.code, e.source, e.line) for e in body.errors).items():
        stmt = insert(ClientErrorCount).values(
            day=day, platform=body.platform, build=body.build, code=code, source=source, line=line, count=count
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["day", "platform", "build", "code", "source", "line"], set_={"count": ClientErrorCount.count + count}
            )
        )
    cleanup(db, commit=False)
    db.commit()
    return {"accepted": len(body.events) + len(body.errors), "duplicate": False}


def cleanup(db: Session, *, commit=True):
    for model in (UsageBatch, UsageCounter, ClientErrorCount):
        db.execute(delete(model).where(model.day < today_msk() - timedelta(days=29)))
    if commit:
        db.commit()


def summary(db: Session):
    since = today_msk() - timedelta(days=29)
    counts = db.execute(
        select(UsageCounter.metric, UsageCounter.bucket, func.sum(UsageCounter.count))
        .where(UsageCounter.day >= since)
        .group_by(UsageCounter.metric, UsageCounter.bucket)
    ).all()
    platforms = db.execute(
        select(UsageCounter.platform, func.sum(UsageCounter.count)).where(UsageCounter.day >= since).group_by(UsageCounter.platform)
    ).all()
    errors = db.execute(
        select(
            ClientErrorCount.platform,
            ClientErrorCount.build,
            ClientErrorCount.code,
            ClientErrorCount.source,
            ClientErrorCount.line,
            func.sum(ClientErrorCount.count).label("count"),
        )
        .where(ClientErrorCount.day >= since)
        .group_by(ClientErrorCount.platform, ClientErrorCount.build, ClientErrorCount.code, ClientErrorCount.source, ClientErrorCount.line)
        .order_by(func.sum(ClientErrorCount.count).desc())
        .limit(20)
    ).all()
    return {
        "since": str(since),
        "retention_days": 30,
        "events": [{"metric": m, "bucket": b, "count": n} for m, b, n in counts],
        "platforms": dict(platforms),
        "errors": [dict(row._mapping) for row in errors],
    }
