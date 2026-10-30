"""«Обратная связь»: приём отчётов (гости, multipart, ≤5/час с IP). Просмотр — только разработчиками (tools/feedback_export.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..services import feedback as svc

router = APIRouter(tags=["feedback"])


async def _read_body(request: Request) -> bytes:
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > svc.MAX_BODY:
        raise HTTPException(413, "Слишком большой запрос")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > svc.MAX_BODY:
            raise HTTPException(413, "Слишком большой запрос")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/api/feedback", status_code=201)
async def post_feedback(request: Request):
    body = await _read_body(request)
    try:
        fields, files = svc.parse_form(request.headers.get("content-type", ""), body)
        if fields.get("website"):  # honeypot: боты заполняют скрытое поле — отвечаем «успехом», ничего не храним
            return {"ok": True}
        data = svc.validate(fields, files)
    except svc.FeedbackError as e:
        raise HTTPException(e.status, str(e)) from None
    ip = request.client.host if request.client else "-"
    if not svc.allow("ip:" + ip):
        raise HTTPException(429, "Слишком много обращений. Попробуйте через час.", headers={"Retry-After": "3600"})
    manifest = await run_in_threadpool(svc.save, data, request.headers.get("host", ""))
    return {"ok": True, "id": manifest["id"]}
