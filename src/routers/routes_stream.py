from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import os
import json
import time
import asyncio

from src.utils.logger import logger
from src.data_models.schemas import ChatCompletionRequest
from src.routers.deps import (
    ChatRequest,
    _validate_api_key,
    _generate_response_id,
    _current_timestamp,
    _create_chunk_dict,
    _determine_log_level,
    _allow_emit,
    _now_iso,
    _prune_history,
    _rows_to_context,
    _forced_web_search_answer,
    _forced_web_search_answer_async,
    _is_insufficient,
    GLOBAL_CHECKPOINTER,
)
from src.utils.tool_events import set_tool_event_emitter, reset_tool_event_emitter


router = APIRouter()


@router.post("/lc/v1/chat/stream")
async def lc_chat_stream(req: ChatRequest, authorization: Optional[str] = Header(None)):
    """
    NOTE: This endpoint previously used sota_trio.py which has been deleted.
    This route needs to be reimplemented with the new agent architecture.
    """
    _validate_api_key(authorization)
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint is temporarily unavailable. The underlying agent (sota_trio) has been removed. Please use the growth_chat agents instead."
    )

    # Dead code below - kept for reference during migration
    async def event_stream():
        response_id = _generate_response_id()
        created_time = _current_timestamp()
        provider = (req.provider or os.environ.get("DEFAULT_LLM_PROVIDER", "vertex_ai"))
        def _default_model_for(p: str) -> str:
            name = (p or "").lower()
            if name in ("openai", "xai", "x-ai", "x_ai", "x.ai", "grok"):
                return os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
            return os.environ.get("VERTEX_DEFAULT_MODEL", "gemini-3-flash-preview")
        model_name = (req.model or _default_model_for(provider))
        use_lg = os.environ.get("USE_LANGGRAPH", "1").lower() in ("1", "true", "yes")
        log_level = _determine_log_level(req.log_level)
        current_agent = "planner"
        node_seq = 0
        tool_seq = 0
        node_stack: list[dict] = []
        node_start_times: dict[str, float] = {}
        tool_stack: list[str] = []
        tool_start_times: dict[str, float] = {}

        planning_chunk = _create_chunk_dict(response_id, created_time, model_name, "### Planning\n\n", True)
        yield "data: " + json.dumps(planning_chunk) + "\n\n"
        if _allow_emit(log_level, "responses"):
            yield "event: response.created\n" + "data: " + json.dumps({
                "type": "response.created",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "created": created_time,
                    "model": model_name,
                }
            }) + "\n\n"

        # NOTE: _create_trio_app has been removed
        app = None
        if use_lg:
            from langchain_core.messages import HumanMessage
            logger.info("Router: streaming LangGraph agent started")
        else:
            logger.info("Router: streaming LangGraph agent started (legacy disabled)")

        try:
            session_id = req.conversation_id or "default"
            _prune_history(session_id)
            streamed_any_text = False
            from src.routers.deps import _trim_input
            safe_query = _trim_input(req.query or "")
            if not safe_query.strip():
                raise HTTPException(status_code=400, detail="Prompt must not be empty")
            # Install per-request tool event emitter
            def _emit(name: str, payload: dict):
                try:
                    payload = dict(payload or {})
                    payload["ts"] = _now_iso()
                    yield_line = "event: tool.event\n" + "data: " + json.dumps({"name": name, "payload": payload}, ensure_ascii=False) + "\n\n"
                    nonlocal _emitted_lines
                    _emitted_lines.append(yield_line)
                except Exception:
                    pass
            _emitted_lines: list[str] = []
            token = set_tool_event_emitter(_emit)

            def _should_stream_text(text: str) -> bool:
                t = (text or "").strip().lower()
                if not t:
                    return False
                control_tokens = {"analyst", "planner", "think", "retriever", "repair", "end", "planning"}
                if t in control_tokens:
                    return False
                if len(t) <= 3 and t.isalpha():
                    return False
                return True

            if use_lg:
                config = {"configurable": {"thread_id": session_id}}
                async for ev in app.astream_events({"messages": [HumanMessage(safe_query)], "iterations": 0}, version="v1", config=config):
                    et = ev.get("event")
                    data = ev.get("data", {})
                    try:
                        logger.info("Stream event: %s", et)
                    except Exception:
                        pass

                    # flush pending tool event lines emitted by tools
                    if _emitted_lines:
                        for ln in _emitted_lines:
                            yield ln
                        _emitted_lines.clear()

                    if et == "on_node_start" and _allow_emit(log_level, "graph"):
                        name = data.get("name") or data.get("node_name") or "node"
                        node_seq += 1
                        node_id = f"node_{node_seq}"
                        node_stack.append({"id": node_id, "name": name})
                        node_start_times[node_id] = time.time()
                        current_agent = name
                        yield "event: graph.step.started\n" + "data: " + json.dumps({
                            "node": name,
                            "checkpoint_id": node_id,
                            "timestamp": _now_iso(),
                        }) + "\n\n"
                        continue

                    if et == "on_node_end" and _allow_emit(log_level, "graph"):
                        name = data.get("name") or data.get("node_name") or (node_stack[-1]["name"] if node_stack else "node")
                        node_id = (node_stack.pop()["id"] if node_stack else None)
                        duration_ms = None
                        if node_id and node_id in node_start_times:
                            duration_ms = int((time.time() - node_start_times.pop(node_id)) * 1000)
                        current_agent = node_stack[-1]["name"] if node_stack else name
                        yield "event: graph.step.completed\n" + "data: " + json.dumps({
                            "node": name,
                            "checkpoint_id": node_id,
                            "timestamp": _now_iso(),
                            "duration_ms": duration_ms,
                        }) + "\n\n"
                        continue

                    if et == "on_tool_start":
                        name = data.get("name", "tool")
                        logger.info("Router: tool start %s", name)
                        args = data.get("input")
                        tool_seq += 1
                        tool_id = f"call_{tool_seq}"
                        tool_stack.append(tool_id)
                        tool_start_times[tool_id] = time.time()
                        try:
                            tool_index = (tool_seq - 1)
                            start_chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": model_name,
                                "choices": [{
                                    "delta": {
                                        "role": "assistant",
                                        "tool_calls": [{
                                            "index": tool_index,
                                            "id": tool_id,
                                            "type": "function",
                                            "function": {"name": name, "arguments": ""}
                                        }]
                                    },
                                    "index": 0,
                                    "finish_reason": None
                                }]
                            }
                            yield "data: " + json.dumps(start_chunk) + "\n\n"
                            try:
                                args_str = json.dumps(args, ensure_ascii=False)
                            except Exception:
                                args_str = str(args)
                            args_chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": model_name,
                                "choices": [{
                                    "delta": {
                                        "tool_calls": [{
                                            "index": tool_index,
                                            "function": {"arguments": args_str}
                                        }]
                                    },
                                    "index": 0,
                                    "finish_reason": None
                                }]
                            }
                            yield "data: " + json.dumps(args_chunk, ensure_ascii=False) + "\n\n"
                        except Exception:
                            pass

                    elif et == "on_tool_end":
                        name = data.get("name", "tool")
                        output = data.get("output")
                        logger.info("Router: tool end %s", name)
                        # Build compact output (not emitted in chat/completions stream)
                        try:
                            if isinstance(output, list):
                                _rows_to_context(output, max_rows=10, max_fields_per_row=12, max_chars_per_value=400, max_total_chars=4000)
                            elif isinstance(output, dict):
                                json.dumps(output, ensure_ascii=False)
                            elif isinstance(output, str):
                                _ = output[:2000]
                            else:
                                json.dumps(output, ensure_ascii=False, default=str)
                        except Exception:
                            pass
                        tool_id = tool_stack.pop() if tool_stack else None
                        if tool_id and tool_id in tool_start_times:
                            _ = int((time.time() - tool_start_times.pop(tool_id)) * 1000)

                    elif et in ("on_chat_model_stream", "on_llm_stream"):
                        chunk = data.get("chunk")
                        text = getattr(chunk, "content", None) if chunk is not None else None
                        # Only stream synthesizer output to avoid showing intermediate executor summaries
                        if isinstance(text, str) and _should_stream_text(text) and current_agent == "synthesize":
                            streamed_any_text = True
                            chunk = _create_chunk_dict(response_id, created_time, model_name, text)
                            yield "data: " + json.dumps(chunk) + "\n\n"
                            if _allow_emit(log_level, "responses"):
                                yield "event: response.output_text.delta\n" + "data: " + json.dumps({"delta": text}, ensure_ascii=False) + "\n\n"

                    elif et == "on_chain_end":
                        output = data.get("output", {})
                        ft = output.get("output") if isinstance(output, dict) else output
                        final_text = str(ft) if ft is not None else ""
                        control_tokens = {"analyst", "planner", "think", "retriever", "repair", "end", "planning"}
                        if isinstance(final_text, str) and final_text.strip().lower() in control_tokens:
                            final_text = ""
                        if (not isinstance(final_text, str)) or (len(final_text.strip()) <= 3):
                            try:
                                msgs = output.get("messages") if isinstance(output, dict) else None
                                if isinstance(msgs, list) and msgs:
                                    for m in reversed(msgs):
                                        text = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
                                        if isinstance(text, str) and text.strip():
                                            final_text = text
                                            break
                            except Exception:
                                pass
                        if isinstance(final_text, str) and final_text.strip():
                            used_fallback = False
                            final_text_lower = final_text.lower()
                            needs_fallback = (
                                _is_insufficient(final_text) or
                                "no results found" in final_text_lower or
                                "not available in our database" in final_text_lower or
                                "i don't have this data" in final_text_lower or
                                "i don't have data" in final_text_lower or
                                "no data available" in final_text_lower
                            )
                            if needs_fallback:
                                fb_provider = os.environ.get("DEFAULT_LLM_PROVIDER", "openai")
                                fb_model = os.environ.get("VERTEX_DEFAULT_MODEL", "gpt-5-mini")
                                try:
                                    fallback = await _forced_web_search_answer_async(req.query, fb_provider, fb_model)
                                except Exception:
                                    fallback = ""
                                if fallback:
                                    final_text = fallback
                                    used_fallback = True
                                    # Flush any tool events emitted by web_search
                                    if _emitted_lines:
                                        for ln in _emitted_lines:
                                            yield ln
                                        _emitted_lines.clear()
                            # Only log first 100 chars to reduce overhead
                            logger.info("Router: final answer to client (stream): %s", final_text[:100] + "..." if len(final_text) > 100 else final_text)
                            if used_fallback or not streamed_any_text:
                                message = "\n\n---\n\n" + final_text
                                chunk = _create_chunk_dict(response_id, created_time, model_name, message)
                                yield "data: " + json.dumps(chunk) + "\n\n"
                            if _allow_emit(log_level, "responses"):
                                yield "event: response.completed\n" + "data: " + json.dumps({"id": response_id, "type": "response.completed"}) + "\n\n"

            final_message = {
                'id': response_id,
                'object': 'chat.completion.chunk',
                'created': created_time,
                'model': model_name,
                'choices': [{
                    'delta': {},
                    'index': 0,
                    'finish_reason': 'stop'
                }]
            }
            yield "data: " + json.dumps(final_message) + "\n\n"
            yield "data: [DONE]\n\n"
            # Reset emitter
            try:
                reset_tool_event_emitter(token)
            except Exception:
                pass

        except Exception as e:
            logger.error("Router: stream error: %s", e, exc_info=True)
            err = f"Error: {str(e)}"
            chunk = _create_chunk_dict(response_id, created_time, model_name, err)
            yield "data: " + json.dumps(chunk) + "\n\n"
            try:
                yield "event: error\n" + "data: " + json.dumps({
                    "code": "server_error",
                    "message": str(e),
                    "timestamp": _now_iso(),
                }) + "\n\n"
            except Exception:
                pass
            final_error = {
                'id': response_id,
                'object': 'chat.completion.chunk',
                'created': created_time,
                'model': model_name,
                'choices': [{
                    'delta': {},
                    'index': 0,
                    'finish_reason': 'error'
                }]
            }
            yield f"data: {json.dumps(final_error)}\n\n"
            try:
                reset_tool_event_emitter(token)
            except Exception:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def compat_openai_chat_completions(payload: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    """
    NOTE: This endpoint previously used sota_trio.py which has been deleted.
    This route needs to be reimplemented with the new agent architecture.
    """
    _validate_api_key(authorization)
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint is temporarily unavailable. The underlying agent (sota_trio) has been removed. Please use the growth_chat agents instead."
    )


