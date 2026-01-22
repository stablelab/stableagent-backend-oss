from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import os
import json

from src.utils.logger import logger
from src.routers.deps import (
    _validate_api_key,
    _generate_response_id,
    _current_timestamp,
    _determine_log_level,
    _allow_emit,
    _now_iso,
    _prune_history,
    _rows_to_context,
    _forced_web_search_answer,
    _is_insufficient,
    GLOBAL_CHECKPOINTER,
)
from src.utils.tool_events import set_tool_event_emitter, reset_tool_event_emitter


router = APIRouter()


@router.post("/v1/responses")
async def compat_openai_responses(payload: dict, authorization: Optional[str] = Header(None)):
    """
    NOTE: This endpoint previously used sota_trio.py which has been deleted.
    This route needs to be reimplemented with the new agent architecture.
    """
    _validate_api_key(authorization)
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint is temporarily unavailable. The underlying agent (sota_trio) has been removed. Please use the growth_chat agents instead."
    )


