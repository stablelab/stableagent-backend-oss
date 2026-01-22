from fastapi import APIRouter, Header
import os

from src.routers.deps import (
    RunRequest,
    _validate_api_key,
    _determine_log_level,
    _approx_tokens,
    GLOBAL_CHECKPOINTER,
)


router = APIRouter()


def _now_iso():  # lightweight local to avoid import loop
    from datetime import datetime, timezone as dt_timezone
    try:
        iso = datetime.now(dt_timezone.utc).isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        return iso
    except Exception:
        return ""


def _make_run_envelope(
    run_id: str,
    thread_id: str,
    provider: str,
    model_name: str,
    log_level: str,
    started_iso: str,
    completed_iso: str,
    final_text: str,
):
    return {
        "version": "1.0",
        "run": {
            "run_id": run_id,
            "thread_id": thread_id,
            "graph_id": "trio-agent",
            "status": "completed",
            "started_at": started_iso,
            "completed_at": completed_iso,
            "model": {"provider": provider, "name": model_name},
            "log_level": log_level,
        },
        "final": {
            "messages": [
                {"role": "assistant", "content": [{"type": "text", "text": final_text}]}
            ]
        },
        "items": [],
        "snapshots": [],
        "usage": {},
        "errors": [],
    }


@router.post("/agent/run")
async def agent_run(payload: RunRequest, authorization: str | None = Header(None)):
    """
    NOTE: This endpoint previously used sota_trio.py which has been deleted.
    This route needs to be reimplemented with the new agent architecture.
    """
    from fastapi import HTTPException
    _validate_api_key(authorization)
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint is temporarily unavailable. The underlying agent (sota_trio) has been removed. Please use the growth_chat agents instead."
    )


