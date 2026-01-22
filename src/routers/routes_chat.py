from fastapi import APIRouter, Header, HTTPException
import os
import json

from src.routers.deps import (
    ChatRequest,
    _validate_api_key,
    GLOBAL_CHECKPOINTER,
    _is_insufficient,
    _forced_web_search_answer,
)


router = APIRouter()


@router.post("/lc/v1/chat")
async def lc_chat(req: ChatRequest, authorization: str | None = Header(None)):
    """
    NOTE: This endpoint previously used sota_trio.py which has been deleted.
    This route needs to be reimplemented with the new agent architecture.
    """
    _validate_api_key(authorization)
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint is temporarily unavailable. The underlying agent (sota_trio) has been removed. Please use the growth_chat agents instead."
    )


