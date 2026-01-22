from __future__ import annotations

from typing import Optional
from typing import List, Dict, Any
from datetime import datetime, timezone as dt_timezone
import os
import time
import uuid
import json
import hashlib

from fastapi import HTTPException

from src.utils.logger import logger
from src.utils.checkpointer import get_checkpointer
from src.pipelines.rag_answer import answer_with_context
from src.tools.sql_generator_tool import SQLQueryTool
from src.tools.context_expander_tool import ContextExpanderTool
from src.knowledge.database_context import DATABASE_CONTEXT
from pydantic import BaseModel
from src.llm.factory import create_chat_model

# Simple fallback cache to avoid repeated web searches
_FALLBACK_CACHE: Dict[str, Dict[str, Any]] = {}
_FALLBACK_CACHE_MAX_SIZE = 100
_FALLBACK_CACHE_TTL = 3600  # 1 hour


def _get_cache_key(query: str) -> str:
    """Generate a cache key for the query"""
    return hashlib.md5(query.lower().strip().encode()).hexdigest()


def _is_cached_fallback(query: str) -> bool:
    """Check if fallback result is cached and still valid"""
    cache_key = _get_cache_key(query)
    if cache_key not in _FALLBACK_CACHE:
        return False
    
    cached_entry = _FALLBACK_CACHE[cache_key]
    if time.time() - cached_entry["timestamp"] > _FALLBACK_CACHE_TTL:
        # Remove expired entry
        del _FALLBACK_CACHE[cache_key]
        return False
    
    return True


def _get_cached_fallback(query: str) -> Optional[str]:
    """Get cached fallback result if available"""
    cache_key = _get_cache_key(query)
    if cache_key in _FALLBACK_CACHE:
        cached_entry = _FALLBACK_CACHE[cache_key]
        if time.time() - cached_entry["timestamp"] <= _FALLBACK_CACHE_TTL:
            return cached_entry["result"]
        else:
            # Remove expired entry
            del _FALLBACK_CACHE[cache_key]
    return None


def _cache_fallback_result(query: str, result: str) -> None:
    """Cache fallback result"""
    cache_key = _get_cache_key(query)
    
    # Clean up cache if it's getting too large
    if len(_FALLBACK_CACHE) >= _FALLBACK_CACHE_MAX_SIZE:
        # Remove oldest entries
        oldest_keys = sorted(_FALLBACK_CACHE.keys(), 
                           key=lambda k: _FALLBACK_CACHE[k]["timestamp"])[:10]
        for key in oldest_keys:
            del _FALLBACK_CACHE[key]
    
    _FALLBACK_CACHE[cache_key] = {
        "result": result,
        "timestamp": time.time()
    }


# Shared FastAPI router dependencies and helpers


class ChatRequest(BaseModel):
    query: str
    provider: Optional[str] = None
    model: Optional[str] = None
    conversation_id: Optional[str] = None
    log_level: Optional[str] = None  # minimal | info | debug


class RunRequest(ChatRequest):
    pass


def _required_api_key() -> Optional[str]:
    return os.environ.get("STABLELAB_TOKEN")


def _validate_api_key(auth_header: Optional[str]):
    required = _required_api_key()
    if not required:
        logger.error("Router: missing STABLELAB_TOKEN in environment")
        raise HTTPException(status_code=500, detail={
            "error": {
                "message": "Server missing API key configuration.",
                "type": "server_error",
                "param": None,
                "code": None
            }
        })
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Router: missing or malformed Authorization header")
        raise HTTPException(status_code=401, detail={
            "error": {
                "message": "You didn't provide an API key.",
                "type": "invalid_request_error",
                "param": None,
                "code": None
            }
        })
    token_value = auth_header.split("Bearer ")[-1].strip()
    if token_value != required:
        logger.warning("Router: incorrect API key provided. Got: %s, Expected: %s", token_value, required)
        raise HTTPException(status_code=401, detail={
            "error": {
                "message": "Incorrect API key provided.",
                "type": "invalid_request_error",
                "param": None,
                "code": None
            }
        })


def _generate_response_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def _current_timestamp() -> int:
    return int(time.time())


def _create_chunk_dict(response_id: str, created_time: int, model_name: str, content: str, role: bool = False) -> dict:
    delta = {"content": content}
    if role:
        delta["role"] = "assistant"
    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model_name,
        "choices": [{
            "delta": delta,
            "index": 0,
            "finish_reason": None
        }]
    }


def _now_iso() -> str:
    try:
        iso = datetime.now(dt_timezone.utc).isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        return iso
    except Exception:
        return ""


def _trim_input(text: str) -> str:
    try:
        max_chars = int(os.environ.get("INPUT_MAX_CHARS", "200000"))
    except Exception:
        max_chars = 200000
    if not isinstance(text, str):
        return ""
    if len(text) > max_chars:
        logger.warning("Router: trimming user input from %d to %d chars to avoid token overflow", len(text), max_chars)
        return text[:max_chars]
    return text


def _determine_log_level(val: Optional[str]) -> str:
    try:
        v = (val or os.environ.get("STREAM_LOG_LEVEL") or "info").strip().lower()
        return v if v in ("minimal", "info", "debug") else "info"
    except Exception:
        return "info"


def _allow_emit(level: str, kind: str) -> bool:
    # kind: "responses" | "run_items" | "graph"
    if level == "minimal":
        return kind == "responses"
    if level == "info":
        return kind in ("responses", "run_items")
    # debug
    return True


def _prune_history(session_id: str, max_messages: int = 40, max_total_chars: int = 120000) -> None:
    # No-op with LangGraph default. Left for compatibility; safe to remove later.
    return


def _rows_to_context(
    rows: list[dict],
    max_rows: int = 20,
    max_fields_per_row: int = 16,
    max_chars_per_value: int = 500,
    max_total_chars: int = 20000,
) -> str:
    try:
        total_chars = 0
        lines: list[str] = []
        for raw in (rows or [])[: max_rows]:
            if not isinstance(raw, dict):
                continue
            keys = list(raw.keys())[: max_fields_per_row]
            compact: dict[str, object] = {}
            for k in keys:
                v = raw.get(k)
                if isinstance(v, (dict, list)):
                    continue
                if isinstance(v, (int, float)):
                    compact[k] = v
                else:
                    s = str(v) if v is not None else ""
                    if len(s) > max_chars_per_value:
                        s = s[: max_chars_per_value] + "…"
                    compact[k] = s
            line = json.dumps(compact, ensure_ascii=False)
            if total_chars + len(line) + 1 > max_total_chars:
                break
            lines.append(line)
            total_chars += len(line) + 1
        return "\n".join(lines)
    except Exception:
        return (str(rows) if rows is not None else "")[: max_total_chars]


def _fallback_answer(user_query: str, provider: str | None, model: str | None) -> str:
    try:
        tool = SQLQueryTool()
        # Expand query context to improve recall
        extra_context = ""
        try:
            expander = ContextExpanderTool()
            expansions = expander._run(user_query)
            if isinstance(expansions, str) and expansions.strip():
                extra_context = "Expanded terms:\n" + expansions.strip()
        except Exception:
            pass
        # Provide schema to the SQL generator
        extra_context = (extra_context + ("\n\nSchema (for reference):\n" + DATABASE_CONTEXT)).strip()
        rows = tool.invoke({"user_query": user_query, "additional_context": extra_context})
        if rows and isinstance(rows, list):
            ctx = _rows_to_context(rows)
            return answer_with_context(user_query, ctx, provider=provider, model_id=model)
    except Exception as e:
        logger.error("Fallback: error generating SQL/context: %s", e, exc_info=True)
    return ""


async def _forced_web_search_answer_async(user_query: str, provider: Optional[str], model: Optional[str]) -> str:
    """Force a web search and synthesize an answer with inline citations.

    Uses SotaWebSearchTool to retrieve web results and summarizes them using the
    same chat provider/model as the primary agent to avoid requiring extra API keys.
    """
    try:
        # Import locally to avoid heavy imports on module import
        from src.tools.sota_web_search import SotaWebSearchTool
    except Exception as e:
        logger.error("WebSearch: tool import error: %s", e, exc_info=True)
        return ""

    try:
        tool = SotaWebSearchTool()
        out: Dict[str, Any] = await tool._arun(query=user_query, k=10, time_range=None, news=False, fetch_full_content=True)
        results: List[Dict[str, Any]] = out.get("results") or []
        if not results:
            return ""

        # Prepare compact, cited context
        bullets: List[str] = []
        for i, r in enumerate(results[:8], 1):
            title = str(r.get("title") or r.get("url") or f"Source {i}")
            url = str(r.get("url") or "")
            body = str(r.get("content") or r.get("snippet") or "").strip()
            if len(body) > 1200:
                body = body[:1200] + "…"
            bullets.append(f"[{i}] {title}\nURL: {url}\n---\n{body}")

        prompt = (
            "You are a careful researcher. Answer the question using ONLY the sources below.\n"
            "Include inline citations like [1], [2] that map to the numbered sources.\n\n"
            f"Question: {user_query}\n\nSources:\n" + "\n".join(bullets)
        )

        llm = create_chat_model(provider=provider, model=model)
        answer = await llm.ainvoke(prompt)
        content = getattr(answer, "content", None)
        return str(content) if content is not None else ""
    except Exception as e:
        logger.error("WebSearch: error during forced search/summarize: %s", e, exc_info=True)
        return ""


def _forced_web_search_answer(user_query: str, provider: Optional[str], model: Optional[str]) -> str:
    """Synchronous variant of forced web search for non-async contexts."""
    try:
        from src.tools.sota_web_search import SotaWebSearchTool
    except Exception as e:
        logger.error("WebSearch: tool import error: %s", e, exc_info=True)
        return ""

    try:
        tool = SotaWebSearchTool()
        out: Dict[str, Any] = tool._run(query=user_query, k=10, time_range=None, news=False, fetch_full_content=True)
        results: List[Dict[str, Any]] = out.get("results") or []
        if not results:
            return ""

        bullets: List[str] = []
        for i, r in enumerate(results[:8], 1):
            title = str(r.get("title") or r.get("url") or f"Source {i}")
            url = str(r.get("url") or "")
            body = str(r.get("content") or r.get("snippet") or "").strip()
            if len(body) > 1200:
                body = body[:1200] + "…"
            bullets.append(f"[{i}] {title}\nURL: {url}\n---\n{body}")

        prompt = (
            "You are a careful researcher. Answer the question using ONLY the sources below.\n"
            "Include inline citations like [1], [2] that map to the numbered sources.\n\n"
            f"Question: {user_query}\n\nSources:\n" + "\n".join(bullets)
        )

        llm = create_chat_model(provider=provider, model=model)
        answer = llm.invoke(prompt)
        content = getattr(answer, "content", None)
        return str(content) if content is not None else ""
    except Exception as e:
        logger.error("WebSearch: error during forced search/summarize (sync): %s", e, exc_info=True)
        return ""


def _is_insufficient(text: str) -> bool:
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    hints = [
        "insufficient context",
        "insufficient information",
        "insufficient data",
        "not enough context",
        "not enough information",
        "not enough data",
        "missing context",
        "missing information",
        "lack of context",
        "lack of information",
        "no sufficient context",
        "no sufficient information",
        "need more context",
        "need more information",
        "need additional context",
        "need additional information",
        "without more context",
        "without additional context",
        "without more information",
        "without additional information",
        "outside the provided context",
        "outside of the provided context",
        "not provided in the context",
        "not present in the context",
        "context not provided",
        "context not sufficient",
        "data not available",
        "information not available",
        "no information provided",
        "no data provided",
        "i don't have enough",
        "i do not have enough",
        "i dont have enough",
        "i don't know",
        "i do not know",
        "i dont know",
        "i'm not sure",
        "i am not sure",
        "im not sure",
        "unsure",
        "uncertain",
        "unclear",
        "unable to answer",
        "cannot answer",
        "can't answer",
        "cannot determine",
        "can't determine",
        "unable to determine",
        "cannot provide a definitive answer",
        "cannot provide an answer",
        "not specified in the context",
        "could not be answered",
        "could not be determined",
        "could not be provided",
        "could not be found",
        "could not be retrieved",
        "could not be fetched",
        "could not be retrieved",
    ]
    return any(h in lowered for h in hints)


def _approx_tokens(text: str) -> int:
    try:
        # Rough heuristic: 1 token ≈ 4 chars (English)
        return max(0, int(len(text or "") / 4))
    except Exception:
        return 0


# Global checkpointer reused across requests so conversation_id threads persist
GLOBAL_CHECKPOINTER = get_checkpointer()


