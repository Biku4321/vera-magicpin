"""
POST /v1/context — store merchant / trigger / customer / category context.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.models import ContextRequest, ContextResponse

router = APIRouter()


@router.post("/context", response_model=ContextResponse)
async def store_context(req: ContextRequest, request: Request):
    store = request.app.state.store

    accepted = await store.set_context(
        scope=req.scope.value,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload,
    )

    return ContextResponse(
        accepted=accepted,
        ack_id=store.make_ack_id(),
        stored_at=datetime.now(timezone.utc).isoformat(),
    )
