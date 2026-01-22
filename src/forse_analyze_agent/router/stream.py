"""Streaming adapter for LangGraph to Vercel AI SDK format.

Provides streaming functions for:
- Standard chat streaming (stream_agent_response)
- Streaming with pre-configured initial state (stream_with_initial_state)
"""

import json
import traceback
import uuid
from typing import Any, AsyncIterator, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.forse_analyze_agent.graph import forse_agent_graph
from src.forse_analyze_agent.utils.converter import convert_to_langchain_messages


async def stream_with_initial_state(
    user_message: str,
    initial_state: Optional[Dict[str, Any]] = None,
    protocol: str = "data",
) -> AsyncIterator[str]:
    """Stream agent response with pre-configured initial state.
    
    Used for direct analysis endpoints where dashboard_id, graph_id,
    and analysis_mode are known upfront.
    
    Args:
        user_message: The user's analysis request
        initial_state: Pre-configured state (dashboard_id, graph_id, analysis_mode, etc.)
        protocol: Streaming protocol (default: "data")
        
    Yields:
        SSE formatted strings for Vercel AI SDK
    """
    # Build input with initial state
    graph_input = {
        "messages": [HumanMessage(content=user_message)],
        **(initial_state or {}),
    }
    
    # Use the core streaming logic
    async for chunk in _stream_graph_execution(graph_input):
        yield chunk


async def stream_agent_response(
    messages: list,
    protocol: str = "data",
) -> AsyncIterator[str]:
    """Stream LangGraph execution as Vercel AI SDK SSE format.
    
    Used for standard chat where messages come from frontend.
    """
    # Convert messages to LangChain format
    langchain_messages = convert_to_langchain_messages(messages)
    
    # Use the core streaming logic
    async for chunk in _stream_graph_execution({"messages": langchain_messages}):
        yield chunk


async def _stream_graph_execution(
    graph_input: Dict[str, Any],
    protocol: str = "data",
) -> AsyncIterator[str]:
    """Core streaming logic for LangGraph execution.
    
    Handles SSE formatting for Vercel AI SDK compatibility.
    
    Args:
        graph_input: Input dict for the graph (messages + optional state)
        protocol: Streaming protocol
        
    Yields:
        SSE formatted strings
    """
    try:

        def format_sse(payload: dict) -> str:
            return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"

        message_id = f"msg-{uuid.uuid4().hex}"
        text_stream_id = "text-1"
        text_started = False
        text_finished = False
        finish_reason = None
        tool_calls_state: Dict[str, Dict[str, Any]] = {}
        text_buffer = ""
        last_ai_message = None

        yield format_sse({"type": "start", "messageId": message_id})

        # Stream the graph execution using astream_events for better streaming
        config = {"configurable": {"thread_id": message_id}}

        # Stream events from the graph
        async for event in forse_agent_graph.astream_events(
            graph_input,
            config=config,
            version="v2",
        ):
            event_name = event.get("event")
            event_data = event.get("data", {})

            # Handle LLM token streaming
            if event_name == "on_chat_model_stream":
                chunk = event_data.get("chunk")

                if chunk:
                    # Handle content delta
                    if hasattr(chunk, "content") and chunk.content:
                        if not text_started:
                            yield format_sse(
                                {"type": "text-start", "id": text_stream_id}
                            )
                            text_started = True

                        delta = chunk.content
                        yield format_sse(
                            {"type": "text-delta", "id": text_stream_id, "delta": delta}
                        )
                        text_buffer += delta

                    # Handle tool call streaming
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tool_call in chunk.tool_calls:
                            tool_call_id = (
                                tool_call.get("id") or f"call_{uuid.uuid4().hex}"
                            )
                            tool_name = tool_call.get("name", "")
                            tool_args = tool_call.get("args", "")

                            if tool_call_id not in tool_calls_state:
                                tool_calls_state[tool_call_id] = {
                                    "id": tool_call_id,
                                    "name": tool_name,
                                    "arguments": "",
                                    "started": False,
                                }

                            state = tool_calls_state[tool_call_id]

                            if tool_name and not state["started"]:
                                yield format_sse(
                                    {
                                        "type": "tool-input-start",
                                        "toolCallId": tool_call_id,
                                        "toolName": tool_name,
                                    }
                                )
                                state["started"] = True
                                state["name"] = tool_name

                            if tool_args:
                                # Handle both string and dict formats (OpenAI vs Gemini)
                                if isinstance(tool_args, dict):
                                    # For dict (Gemini), convert to JSON string
                                    tool_args_str = json.dumps(
                                        tool_args, separators=(",", ":")
                                    )
                                    # Merge with existing arguments if any
                                    try:
                                        existing_args = (
                                            json.loads(state["arguments"])
                                            if state["arguments"]
                                            else {}
                                        )
                                        merged_args = {**existing_args, **tool_args}
                                        tool_args_str = json.dumps(
                                            merged_args, separators=(",", ":")
                                        )
                                    except (json.JSONDecodeError, TypeError):
                                        # If merge fails, just use new args
                                        pass
                                    state["arguments"] = tool_args_str
                                elif isinstance(tool_args, str):
                                    # For string (OpenAI), append incrementally
                                    state["arguments"] += tool_args
                                    tool_args_str = tool_args
                                else:
                                    # Fallback: convert to string
                                    tool_args_str = str(tool_args)
                                    state["arguments"] = tool_args_str

                                yield format_sse(
                                    {
                                        "type": "tool-input-delta",
                                        "toolCallId": tool_call_id,
                                        "inputTextDelta": tool_args_str,
                                    }
                                )

            # Handle final AI message
            elif event_name == "on_chain_end" and event.get("name") == "call_model":
                output = event_data.get("output", {})
                messages = output.get("messages", [])

                for msg in messages:
                    if isinstance(msg, AIMessage):
                        last_ai_message = msg

                        # Handle text content if not already streamed
                        if (
                            msg.content
                            and isinstance(msg.content, str)
                            and msg.content.strip()
                        ):
                            # If we haven't started streaming text yet, emit the full content
                            if not text_started:
                                yield format_sse(
                                    {"type": "text-start", "id": text_stream_id}
                                )
                                text_started = True

                            # Check if content is different from what we've buffered
                            if msg.content != text_buffer:
                                # Emit remaining content as delta
                                remaining = msg.content[len(text_buffer) :]
                                if remaining:
                                    yield format_sse(
                                        {
                                            "type": "text-delta",
                                            "id": text_stream_id,
                                            "delta": remaining,
                                        }
                                    )
                                    text_buffer = msg.content

                        # Handle tool calls
                        if msg.tool_calls:
                            for tool_call in msg.tool_calls:
                                tool_call_id = tool_call.get(
                                    "id", f"call_{uuid.uuid4().hex}"
                                )
                                tool_name = tool_call.get("name", "")
                                tool_args = tool_call.get("args", {})

                                # Ensure tool call is started
                                if tool_call_id not in tool_calls_state:
                                    tool_calls_state[tool_call_id] = {
                                        "id": tool_call_id,
                                        "name": tool_name,
                                        "arguments": "",
                                        "started": False,
                                    }

                                state = tool_calls_state[tool_call_id]

                                if not state["started"]:
                                    yield format_sse(
                                        {
                                            "type": "tool-input-start",
                                            "toolCallId": tool_call_id,
                                            "toolName": tool_name,
                                        }
                                    )
                                    state["started"] = True

                                # Parse arguments
                                try:
                                    if isinstance(tool_args, str):
                                        parsed_args = json.loads(tool_args)
                                    else:
                                        parsed_args = tool_args

                                    yield format_sse(
                                        {
                                            "type": "tool-input-available",
                                            "toolCallId": tool_call_id,
                                            "toolName": tool_name,
                                            "input": parsed_args,
                                        }
                                    )
                                except Exception as error:
                                    yield format_sse(
                                        {
                                            "type": "tool-input-error",
                                            "toolCallId": tool_call_id,
                                            "toolName": tool_name,
                                            "input": tool_args,
                                            "errorText": str(error),
                                        }
                                    )

            # Handle tool results
            elif event_name == "on_chain_end" and event.get("name") == "tools":
                output = event_data.get("output", {})
                messages = output.get("messages", [])

                for msg in messages:
                    if isinstance(msg, ToolMessage):
                        tool_call_id = msg.tool_call_id
                        tool_result = msg.content

                        try:
                            if isinstance(tool_result, str):
                                try:
                                    parsed_result = json.loads(tool_result)
                                except json.JSONDecodeError:
                                    parsed_result = tool_result
                            else:
                                parsed_result = tool_result

                            yield format_sse(
                                {
                                    "type": "tool-output-available",
                                    "toolCallId": tool_call_id,
                                    "output": parsed_result,
                                }
                            )
                        except Exception as error:
                            yield format_sse(
                                {
                                    "type": "tool-output-error",
                                    "toolCallId": tool_call_id,
                                    "errorText": str(error),
                                }
                            )

        # Determine finish reason
        if last_ai_message:
            if last_ai_message.tool_calls:
                finish_reason = "tool_calls"
            else:
                finish_reason = "stop"
        else:
            finish_reason = "stop"

        # Finish text if started
        if text_started and not text_finished:
            yield format_sse({"type": "text-end", "id": text_stream_id})
            text_finished = True

        # Send finish event
        finish_metadata: Dict[str, Any] = {}
        if finish_reason:
            finish_metadata["finishReason"] = finish_reason.replace("_", "-")

        yield format_sse({"type": "finish", "messageMetadata": finish_metadata})
        yield "data: [DONE]\n\n"

    except Exception:
        traceback.print_exc()
        raise
