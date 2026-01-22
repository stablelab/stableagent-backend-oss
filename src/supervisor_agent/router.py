"""
FastAPI router for supervisor agent endpoints.

The supervisor agent orchestrates multiple specialized agents (forse_analyze, knowledge_base, math).
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field
import json
import uuid

from src.auth.deps import get_current_user
from src.utils.logger import logger
from .workflow import supervisor_app

# router = APIRouter(dependencies=[Depends(get_current_user)])
router = APIRouter()


class MessagePart(BaseModel):
    """Vercel AI SDK message part."""
    type: str
    text: Optional[str] = None
    contentType: Optional[str] = None
    url: Optional[str] = None
    data: Optional[Any] = None
    toolCallId: Optional[str] = None
    toolName: Optional[str] = None
    state: Optional[str] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    args: Optional[Any] = None


class VercelMessage(BaseModel):
    """Vercel AI SDK message format."""
    role: str
    parts: Optional[List[MessagePart]] = None
    content: Optional[str] = None
    id: Optional[str] = None


class SupervisorQueryRequest(BaseModel):
    """
    Vercel AI SDK compatible request format.
    
    Attributes:
        id: Request ID
        messages: List of messages with parts
        trigger: Trigger type (e.g., "submit-message")
    """
    id: Optional[str] = None
    messages: List[VercelMessage] = Field(..., description="List of messages")
    trigger: Optional[str] = Field(None, description="Trigger type")


@router.post("/chat")
async def query_supervisor(
    query_request: SupervisorQueryRequest,
    request: Request,
    org_id: Optional[int] = Query(None, description="Organization ID (for knowledge agent context)"),
    org_schema: Optional[str] = Query(None, description="Organization schema (for knowledge agent context)"),
    stream: Optional[bool] = Query(None, description="Whether to stream the response")
):
    """
    Query the supervisor agent with a natural language question.
    
    Accepts Vercel AI SDK compatible request format:
    {
        "id": "001",
        "messages": [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "..."}]
            }
        ],
        "trigger": "submit-message"
    }
    
    The supervisor will route the query to the appropriate specialized agent:
    - forse_analyze_agent: For DAO/proposal analysis
    - knowledge_agent: For knowledge base queries
    
    Args:
        query_request: Vercel AI SDK compatible request
        request: FastAPI request object (contains authenticated user)
        org_id: Optional organization ID (query parameter)
        org_schema: Optional organization schema (query parameter)
        stream: Whether to stream (query parameter, defaults to True if Accept header includes text/event-stream)
    
    Returns:
        StreamingResponse (SSE) or JSON response with answer
    """
    # Extract text from messages
    query_text = ""
    for message in query_request.messages:
        if message.role == "user":
            if message.parts:
                # Extract text from parts
                for part in message.parts:
                    if part.type == "text" and part.text:
                        query_text += part.text + " "
            elif message.content:
                query_text += message.content + " "
    
    query_text = query_text.strip()
    
    if not query_text:
        raise HTTPException(
            status_code=400,
            detail="No text content found in messages"
        )
    
    # Determine streaming mode
    # Check query param first, then Accept header, default to True (Vercel AI SDK typically streams)
    accept_header = request.headers.get("accept", "").lower()
    if stream is not None:
        should_stream = stream
    elif "text/event-stream" in accept_header:
        should_stream = True
    else:
        # Default to streaming for Vercel AI SDK compatibility
        should_stream = True
    
    # user = request.state.user
    # logger.info(
    #     f"Supervisor query by user {user.get('sub', 'unknown')}: query='{query_text[:50]}...'"
    # )
    
    # Prepare initial state with messages
    initial_state = {
        "messages": [
            HumanMessage(content=query_text)
        ]
    }
    
    # Store org context in state if provided (for knowledge agent)
    if org_id is not None:
        initial_state["org_id"] = org_id
    if org_schema is not None:
        initial_state["org_schema"] = org_schema
    
    if should_stream:   
        async def event_stream():
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
            
            try:
                # Start event
                yield format_sse({"type": "start", "messageId": message_id})
                
                # Use astream_events for detailed event streaming
                config = {"configurable": {"thread_id": message_id}}
                
                async for event in supervisor_app.astream_events(
                    initial_state,
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
                                        # Handle both string and dict formats
                                        if isinstance(tool_args, dict):
                                            tool_args_str = json.dumps(
                                                tool_args, separators=(",", ":")
                                            )
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
                                                pass
                                            state["arguments"] = tool_args_str
                                        elif isinstance(tool_args, str):
                                            state["arguments"] += tool_args
                                            tool_args_str = tool_args
                                        else:
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
                                    if not text_started:
                                        yield format_sse(
                                            {"type": "text-start", "id": text_stream_id}
                                        )
                                        text_started = True
                                    
                                    # Check if content is different from what we've buffered
                                    if msg.content != text_buffer:
                                        remaining = msg.content[len(text_buffer):]
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
                    
            except Exception as e:
                logger.error(f"Error in supervisor streaming: {str(e)}", exc_info=True)
                error_event = {
                    "type": "error",
                    "error": str(e),
                }
                yield format_sse(error_event)
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        try:
            message_id = f"msg-{uuid.uuid4().hex}"
            config = {"configurable": {"thread_id": message_id}}
            
            # Use ainvoke for non-streaming execution
            final_state = await supervisor_app.ainvoke(initial_state, config=config)
            
            # Extract answer and metadata from messages
            text_content = ""
            tool_calls = []
            finish_reason = "stop"
            last_ai_message = None
            
            if final_state and "messages" in final_state:
                # Find the last AI message
                for message in reversed(final_state["messages"]):
                    if isinstance(message, AIMessage):
                        last_ai_message = message
                        break
                
                if last_ai_message:
                    # Extract text content
                    if hasattr(last_ai_message, "content"):
                        if isinstance(last_ai_message.content, str):
                            text_content = last_ai_message.content
                        elif isinstance(last_ai_message.content, list):
                            # Handle list content (e.g., from tool calls)
                            text_parts = []
                            for item in last_ai_message.content:
                                if isinstance(item, dict) and "text" in item:
                                    text_parts.append(item["text"])
                                elif isinstance(item, str):
                                    text_parts.append(item)
                            text_content = " ".join(text_parts)
                    
                    # Extract tool calls if any
                    if hasattr(last_ai_message, "tool_calls") and last_ai_message.tool_calls:
                        finish_reason = "tool_calls"
                        for tool_call in last_ai_message.tool_calls:
                            tool_call_id = tool_call.get("id", f"call_{uuid.uuid4().hex}")
                            tool_name = tool_call.get("name", "")
                            tool_args = tool_call.get("args", {})
                            
                            # Parse arguments if string
                            if isinstance(tool_args, str):
                                try:
                                    tool_args = json.loads(tool_args)
                                except json.JSONDecodeError:
                                    pass
                            
                            tool_calls.append({
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                                }
                            })
            
            response = {
                "id": message_id,
                "text": text_content,
                "finishReason": finish_reason,
            }
            
            # Add tool calls if present
            if tool_calls:
                response["toolCalls"] = tool_calls
            
            return response
            
        except Exception as e:
            logger.error(f"Error in supervisor query: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
