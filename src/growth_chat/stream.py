"""
Streaming functionality for Growth Chat Super Graph.

Provides granular streaming of agent execution,
yielding results compatible with KnowledgeRAGResult format.
Handles both knowledge_hub and grants_admin agent streams.
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.utils.langsmith import create_thread_config
from src.utils.logger import logger
from src.utils.model_factory import extract_text_content

from .exceptions import (AuthenticationError, AuthorizationError,
                         CheckpointerError, DatabaseConnectionError,
                         GatewayTimeoutError, GrowthChatError, InternalError,
                         RateLimitError, ResourceNotFoundError,
                         ValidationError, classify_exception,
                         is_retryable_exception)
from .file_processor import format_files_for_context, process_files
from .graph import create_growth_chat_graph
from .knowledge_base_agent.types import (GrowthChatResult, KnowledgeItem,
                                         ToolInvocation)
from .schemas import AgentType, AttachedFile, UserInfo

# Global variable to track the last message count per conversation
_last_message_counts: Dict[str, int] = {}


async def stream_processing(
    message: str,
    conversation_id: str,
    auth_token: str,
    org_id: int,
    org_schema: str,
    org_slug: str,
    knowledge_visibility: Optional[str] = None,
    user_info: Optional[UserInfo] = None,
    attached_files: Optional[list[AttachedFile]] = None,
) -> AsyncGenerator[GrowthChatResult, None]:
    """
    Stream Growth Chat processing with progressive results.
    
    Uses astream to stream state updates after each node execution.
    Detects which agent is running and yields appropriate results.
    
    Args:
        message: User's input message
        conversation_id: Conversation ID for checkpointer (thread_id)
        auth_token: Authentication token for API calls
        org_id: Organization ID for knowledge base queries
        org_schema: Organization schema name
        org_slug: Organization slug
        knowledge_visibility: Visibility filter for knowledge hub ("public" or None for all)
        user_info: User information (id, handle, email, display_name)
        attached_files: Files attached to this message (stored in GCS)
    Yields:
        KnowledgeRAGResult with appropriate stage based on current node
    """
    start_time = time.time()
    
    logger.info(
        f"Starting growth_chat stream processing for message: '{message[:50]}...' "
        f"(conversation_id={conversation_id}, org_id={org_id})"
    )
    
    try:
        # Create graph with auth token and org context
        graph = create_growth_chat_graph(
            auth_token, org_id, org_slug, org_schema,
            knowledge_visibility=knowledge_visibility,
            user_info=user_info,
        )
        
        # Config for checkpointer
        # recursion_limit must be >= 2 * MAX_TOOL_CALLS + 3 to allow final answer
        # Each tool call = 2 nodes (model→tools), plus final model to answer
        max_tools = int(os.getenv("RESEARCH_AGENT_MAX_TOOLS", "6"))
        min_recursion = 2 * max_tools + 3  # 6 tools = 15 minimum
        
        # Create LangSmith thread config for tracing
        user_id = user_info.get("id") if user_info else None
        thread_config = create_thread_config(conversation_id, user_id)
        
        config = {
            "configurable": {"thread_id": conversation_id},
            "recursion_limit": max(min_recursion, int(os.getenv("LANGGRAPH_MAX_ITERS", 20))),
            **thread_config  # Merge langsmith callbacks, metadata, tags
        }
        
        # Check for pending interrupts (approval flow)
        current_state = await graph.aget_state(config=config)
        if current_state.interrupts:
            # Treat user message as approval data
            logger.info(f"Interrupts detected, treating user msg as approval data: {message}")
            try:
                approval_data = json.loads(message)
                initial_state = Command(resume=approval_data)
            except json.JSONDecodeError:
                logger.error(f"Error parsing approval data: {message}")
                yield GrowthChatResult(
                    stage="answer",
                    query=message,
                    answer=f"❌ Error parsing approval data: {message}.\nTry again with the correct format.",
                    processing_time_ms=(time.time() - start_time) * 1000
                )
                return
        else:
            # Normal message flow
            # Process attached files if any
            file_context = ""
            if attached_files:
                logger.info(f"Processing {len(attached_files)} attached files")
                processed_files = process_files(attached_files)
                file_context = format_files_for_context(processed_files)
                logger.info(f"File context generated: {len(file_context)} chars")
            
            # Prepend file context to message if available
            full_message = message
            if file_context:
                full_message = f"{file_context}\n\nUser query: {message}"
            
            initial_state: Dict[str, Any] = {
                "messages": [HumanMessage(content=full_message)],
                "org_id": org_id,
                "org_schema": org_schema,
                "auth_token": auth_token,
                "attached_files": attached_files or [],
            }
        
        # Track state for streaming
        has_interrupt = False
        _last_message_counts[conversation_id] = _last_message_counts.get(conversation_id, 1)
        
        # Accumulate documents for this response only (across multiple tool calls)
        kb_accumulated_docs = []
        
        # Track plan state for multi-step flows
        plan_length = 1  # Default to single step
        current_step = 0
        
        # Stream state updates from the graph including subgraphs
        async for namespace, event in graph.astream(initial_state, config=config, stream_mode="updates", subgraphs=True):
            # namespace is a tuple of node names representing the path to the current subgraph
            # e.g. () for root, ('forse_agent',) for forse_agent subgraph
            
            node_name = list(event.keys())[0] if event else None
            node_output = event.get(node_name, {}) if node_name else {}
            
            log_namespace = f"{namespace}.{node_name}" if namespace else node_name
            logger.info(f"Stream event from node: {log_namespace}")

            # --- Root Graph Events ---
            if not namespace:
                result = _handle_root_event(
                    node_name=node_name,
                    node_output=node_output,
                    message=message,
                    start_time=start_time,
                    kb_accumulated_docs=kb_accumulated_docs,
                    plan_length=plan_length,
                    current_step=current_step,
                )
                
                # Yield all results
                for r in result.results:
                    yield r
                
                # Update state
                kb_accumulated_docs = result.kb_accumulated_docs
                plan_length = result.plan_length
                current_step = result.current_step
                
                # Handle control flow
                if not result.should_continue:
                    # Interrupt case - break out of the loop
                    if node_name == "__interrupt__":
                        has_interrupt = True
                        break
                else:
                    continue

            # --- Subgraph Events ---
            else:
                result = _handle_subgraph_event(
                    namespace=namespace,
                    node_name=node_name,
                    node_output=node_output,
                    message=message,
                    start_time=start_time,
                    kb_accumulated_docs=kb_accumulated_docs,
                )
                
                # Yield all results
                for r in result.results:
                    yield r
                
                # Update state
                kb_accumulated_docs = result.kb_accumulated_docs
        
        # Log completion
        processing_time = (time.time() - start_time) * 1000
        logger.info(
            f"Growth chat stream processing complete in {processing_time:.1f}ms "
            f"(has_interrupt: {has_interrupt})"
        )
        
    except asyncio.TimeoutError as e:
        logger.error(f"Timeout in growth chat stream processing: {e}", exc_info=True)
        yield GrowthChatResult(
            stage="error",
            query=message,
            error_code=504,
            error_message="Request timed out. The response is being processed in the background.",
            retryable=True,
            processing_time_ms=(time.time() - start_time) * 1000
        )
    
    except asyncio.CancelledError:
        logger.warning(f"Growth chat stream cancelled for conversation {conversation_id}")
        yield GrowthChatResult(
            stage="error",
            query=message,
            error_code=499,  # Client closed request
            error_message="Request was cancelled.",
            retryable=True,
            processing_time_ms=(time.time() - start_time) * 1000
        )
    
    except GrowthChatError as e:
        # Use structured error from our exception hierarchy
        logger.error(f"Growth chat error [{e.code}]: {e.message}", exc_info=True)
        yield GrowthChatResult(
            stage="error",
            query=message,
            error_code=e.code,
            error_message=e.message,
            retryable=e.retryable,
            retry_after=e.retry_after,
            processing_time_ms=(time.time() - start_time) * 1000
        )
    
    except ConnectionError as e:
        logger.error(f"Connection error in growth chat: {e}", exc_info=True)
        yield GrowthChatResult(
            stage="error",
            query=message,
            error_code=503,
            error_message="Database connection failed. Please try again.",
            retryable=True,
            retry_after=5.0,
            processing_time_ms=(time.time() - start_time) * 1000
        )
        
    except Exception as e:
        # Classify unknown exceptions
        classified = classify_exception(e)
        logger.error(
            f"Unexpected error in growth chat [{classified.code}]: {e}", 
            exc_info=True
        )
        
        yield GrowthChatResult(
            stage="error",
            query=message,
            error_code=classified.code,
            error_message=classified.message,
            retryable=classified.retryable,
            retry_after=classified.retry_after,
            processing_time_ms=(time.time() - start_time) * 1000
        )


def _handle_interrupt(node_output: Any, message: str, start_time: float) -> GrowthChatResult:
    """
    Handle interrupt events from grants_admin agent.
    
    Formats the interrupt data into a user-friendly approval request.
    """
    interrupts_list = [
        {
            "id": interrupt.id,
            "value": interrupt.value,
        }
        for interrupt in node_output
    ]
    
    interrupts_str = "\n\n".join([
        f"Action: {interrupt['value']['action']} (ID: {interrupt['id']})\n"
        f"Parameters: {json.dumps(interrupt['value']['parameters'])}\n"
        f"Message: {interrupt['value']['message']}"
        for interrupt in interrupts_list
    ])
    
    approval_string = json.dumps(
        {interrupt["id"]: {"action": "approve"} for interrupt in interrupts_list},
        indent=2
    )
    
    logger.info(f"Detected {len(interrupts_list)} interrupt(s) requiring approval")
    
    return GrowthChatResult(
        stage="answer",
        query=message,
        answer=(
            f"⏸️ Approval required. Please approve or cancel the following actions.\n\n"
            f"{interrupts_str}\n\n"
            f"Approval string:\n{approval_string}"
        ),
        processing_time_ms=(time.time() - start_time) * 1000
    )


def _create_documents_result(
    documents: list,
    message: str,
    start_time: float
) -> GrowthChatResult:
    """
    Create a KnowledgeRAGResult for retrieved documents.
    """
    seen_ids = set()
    knowledge_items = []
    for idx, doc in enumerate(documents):
        doc_id = doc.get("id", idx)
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        knowledge_items.append(
            KnowledgeItem(
                id=doc_id,
                title=doc.get("title", "Untitled"),
                content=doc.get("content", ""),
                source_type=doc.get("source_type", "unknown"),
                source_item_id=doc.get("source_item_id", ""),
                distance=doc.get("distance", 0.0),
                metadata=doc.get("metadata", {}),
                created_at=doc.get("created_at", datetime.utcnow().isoformat()),
                last_synced_at=doc.get("last_synced_at"),
                visibility=doc.get("visibility", "public")
            )
        )
    
    return GrowthChatResult(
        stage="documents",
        query=message,
        documents=knowledge_items,
        total_documents=len(knowledge_items),
        processing_time_ms=(time.time() - start_time) * 1000
    )


def _build_tool_invocation(
    state: str,
    tool_call_id: str,
    tool_name: str,
    args: Optional[Any] = None,
    result: Optional[Any] = None,
) -> ToolInvocation:
    """
    Create a ToolInvocation payload mirroring the router's shape (call/result).
    """
    return ToolInvocation(
        state=state,
        toolCallId=tool_call_id,
        toolName=tool_name,
        args=args,
        result=result,
    )


def _yield_tool_calls_from_message(
    msg: AIMessage,
    message: str,
    start_time: float,
) -> list[GrowthChatResult]:
    """
    Extract tool call events from an AIMessage with tool_calls.
    
    Args:
        msg: AIMessage that may contain tool_calls
        message: Original user query
        start_time: Start time for processing time calculation
        
    Returns:
        List of GrowthChatResult for each tool call
    """
    results = []
    if hasattr(msg, 'tool_calls') and msg.tool_calls:
        for tool_call in msg.tool_calls:
            results.append(GrowthChatResult(
                stage="tool_call",
                query=message,
                tool_invocation=_build_tool_invocation(
                    state="call",
                    tool_call_id=tool_call.get("id", ""),
                    tool_name=tool_call.get("name", ""),
                    args=tool_call.get("args", {}),
                ),
                processing_time_ms=(time.time() - start_time) * 1000
            ))
    return results


def _yield_tool_result_from_message(
    msg: ToolMessage,
    message: str,
    start_time: float,
) -> GrowthChatResult:
    """
    Create a tool result event from a ToolMessage.
    
    Args:
        msg: ToolMessage with tool execution result
        message: Original user query
        start_time: Start time for processing time calculation
        
    Returns:
        GrowthChatResult for the tool result
    """
    # Parse content if it's JSON
    try:
        output = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
    except json.JSONDecodeError:
        output = msg.content
    
    return GrowthChatResult(
        stage="tool_call",
        query=message,
        tool_invocation=_build_tool_invocation(
            state="result",
            tool_call_id=msg.tool_call_id,
            tool_name=msg.name,
            result=output,
        ),
        processing_time_ms=(time.time() - start_time) * 1000
    )


def _yield_step_result(
    node_name: str,
    content: str,
    message: str,
    start_time: float,
) -> GrowthChatResult:
    """
    Create a step result event for an agent's final output.
    
    Args:
        node_name: Name of the node that produced the result
        content: Content of the result
        message: Original user query
        start_time: Start time for processing time calculation
        
    Returns:
        GrowthChatResult for the step result
    """
    return GrowthChatResult(
        stage="tool_call",
        query=message,
        tool_invocation=_build_tool_invocation(
            state="result",
            tool_call_id=str(uuid.uuid4()),
            tool_name=node_name,
            result=content,
        ),
        processing_time_ms=(time.time() - start_time) * 1000
    )


# Agent type constants for routing
_ALL_AGENT_TYPES = (
    AgentType.KNOWLEDGE_HUB.value,
    AgentType.APP_AUTOMATION.value,
    AgentType.ONBOARDING.value,
    AgentType.RESEARCH.value,
    AgentType.FORSE_ANALYZER.value,
    AgentType.CONVERSATION.value,
)


def _is_agent_node(node_name: str) -> bool:
    """Check if node is an agent node (starts with any AgentType value)."""
    return any(node_name.startswith(agent) for agent in _ALL_AGENT_TYPES)


def _get_model_node_name(agent_namespace: str) -> str:
    """
    Get the model node name for a given agent namespace.
    
    Different agent types use different internal node names:
    - most agents: "model"
    - FORSE_ANALYZER: "call_model"
    
    Args:
        agent_namespace: The agent namespace from the event
        
    Returns:
        The model node name for that agent type
    """
    if agent_namespace.startswith(AgentType.FORSE_ANALYZER.value):
        # forse_analyze_agent uses call_model instead of model
        return "call_model"
    else:
        return "model"


class RootEventResult:
    """Result from handling a root event, with state updates."""
    def __init__(
        self,
        results: list[GrowthChatResult],
        kb_accumulated_docs: list,
        plan_length: int,
        current_step: int,
        should_continue: bool = False,
    ):
        self.results = results
        self.kb_accumulated_docs = kb_accumulated_docs
        self.plan_length = plan_length
        self.current_step = current_step
        self.should_continue = should_continue


def _handle_root_event(
    node_name: str,
    node_output: dict,
    message: str,
    start_time: float,
    kb_accumulated_docs: list,
    plan_length: int,
    current_step: int,
) -> RootEventResult:
    """
    Handle root graph events (no namespace).
    
    Handles special nodes and agent result nodes:
    - __interrupt__: Approval flow interrupts
    - planner: Plan creation
    - post_agent: Step transitions
    - summarizer: Final answer
    - suggest_queries: Follow-up suggestions
    - Agent nodes: Final AIMessage without tool_calls as step result
    
    Args:
        node_name: Name of the node
        node_output: Output from the node
        message: Original user query
        start_time: Start time for processing time calculation
        kb_accumulated_docs: Accumulated documents from knowledge hub
        plan_length: Current plan length
        current_step: Current step index
        
    Returns:
        RootEventResult with results and updated state
    """
    results = []
    
    # Handle interrupts (approval flow) - returns with should_continue=False to trigger break
    if node_name == "__interrupt__":
        results.append(_handle_interrupt(node_output, message, start_time))
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=False,
        )
    
    # Handle planner node - emit routing stage
    if node_name == "planner":
        plan = node_output.get("plan", [])
        plan_length = len(plan) if plan else 1
        which_agent = node_output.get("which_agent")
        agent_name = which_agent.value if which_agent else "unknown"
        logger.info(f"Planner created {plan_length}-step plan, starting with: {agent_name}")
        results.append(GrowthChatResult(
            stage="routing",
            query=message,
            routed_agent=agent_name,
            processing_time_ms=(time.time() - start_time) * 1000
        ))
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=True,
        )
    
    # Handle post_agent node - emit when moving to next step
    if node_name == "post_agent":
        current_step = node_output.get("current_step_index", 0)
        which_agent = node_output.get("which_agent")
        if which_agent:
            logger.info(f"Post-agent: moving to step {current_step + 1}/{plan_length}, agent: {which_agent.value}")
            results.append(GrowthChatResult(
                stage="routing",
                query=message,
                routed_agent=which_agent.value,
                processing_time_ms=(time.time() - start_time) * 1000
            ))
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=True,
        )
    
    # Handle summarizer node
    # or onboarding agent - this is the ONLY places we emit "answer".
    if node_name == "summarizer" or node_name.startswith(AgentType.ONBOARDING.value):
        messages = node_output.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage):
            content = extract_text_content(messages[-1].content)
            if content and content.strip():
                results.append(GrowthChatResult(
                    stage="answer",
                    query=message,
                    answer=content.strip(),
                    processing_time_ms=(time.time() - start_time) * 1000
                ))
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=True,
        )
    
    # Handle suggest_queries node
    if node_name == "suggest_queries":
        suggestions = node_output.get("suggested_queries", [])
        if suggestions:
            results.append(GrowthChatResult(
                stage="suggested_queries",
                query=message,
                suggested_queries=suggestions,
                processing_time_ms=(time.time() - start_time) * 1000
            ))
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=True,
        )
    
    # Handle agent nodes - yield final AIMessage without tool_calls as step result
    if _is_agent_node(node_name):
        messages = node_output.get("messages", [])
        
        if messages and isinstance(messages[-1], AIMessage):
            last_msg = messages[-1]
            # Only emit if it's a final answer (no tool calls)
            if not (hasattr(last_msg, 'tool_calls') and last_msg.tool_calls):
                # Special case: yield accumulated documents before knowledge hub result
                if node_name.startswith(AgentType.KNOWLEDGE_HUB.value) and kb_accumulated_docs:
                    results.append(_create_documents_result(kb_accumulated_docs, message, start_time))
                    kb_accumulated_docs = []
                
                content = extract_text_content(last_msg.content)
                if content and content.strip():
                    results.append(_yield_step_result(node_name, content, message, start_time))
        
        return RootEventResult(
            results=results,
            kb_accumulated_docs=kb_accumulated_docs,
            plan_length=plan_length,
            current_step=current_step,
            should_continue=True,
        )
    
    # Unknown node - no results
    return RootEventResult(
        results=results,
        kb_accumulated_docs=kb_accumulated_docs,
        plan_length=plan_length,
        current_step=current_step,
    )


class SubgraphEventResult:
    """Result from handling a subgraph event, with state updates."""
    def __init__(
        self,
        results: list[GrowthChatResult],
        kb_accumulated_docs: list,
    ):
        self.results = results
        self.kb_accumulated_docs = kb_accumulated_docs


def _handle_subgraph_event(
    namespace: tuple,
    node_name: str,
    node_output: dict,
    message: str,
    start_time: float,
    kb_accumulated_docs: list,
) -> SubgraphEventResult:
    """
    Handle subgraph events (events from within agent subgraphs).
    
    Streams tool calls and results from agent internal nodes:
    - Model nodes (agent/model/call_model): yield AIMessages with tool_calls as "call" stage
    - Tools node: yield ToolMessages as "result" stage
    
    Args:
        namespace: Tuple of node names representing the path to the subgraph
        node_name: Name of the node within the subgraph
        node_output: Output from the node
        message: Original user query
        start_time: Start time for processing time calculation
        kb_accumulated_docs: Accumulated documents from knowledge hub
        
    Returns:
        SubgraphEventResult with results and updated kb_accumulated_docs
    """
    results = []
    agent_namespace = namespace[0]
    model_node = _get_model_node_name(agent_namespace)
    
    # Debug logging to understand event flow
    logger.info(f"[Subgraph] namespace={agent_namespace}, node={node_name}")
    
    # Handle model node - yield tool calls in "call" stage
    if node_name == model_node:
        messages = node_output.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage):
            last_msg = messages[-1]
            
            # FORSE special behavior: surface model content before tool calls
            if agent_namespace.startswith(AgentType.FORSE_ANALYZER.value):
                if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                    content = extract_text_content(last_msg.content)
                    if content and content.strip():
                        results.append(GrowthChatResult(
                            stage="answer",
                            query=message,
                            answer=content.strip(),
                            processing_time_ms=(time.time() - start_time) * 1000
                        ))
            
            # Yield tool calls
            for result in _yield_tool_calls_from_message(last_msg, message, start_time):
                results.append(result)
    
    # Handle tools node - yield tool results in "result" stage
    elif node_name == "tools":
        messages = node_output.get("messages", [])
        for msg in messages:
            if isinstance(msg, ToolMessage):
                results.append(_yield_tool_result_from_message(msg, message, start_time))
                
                # Special case: accumulate documents from knowledge hub
                if agent_namespace.startswith(AgentType.KNOWLEDGE_HUB.value):
                    if msg.name == "search_knowledge_hub":
                        try:
                            output = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        except json.JSONDecodeError:
                            output = msg.content
                        if isinstance(output, dict):
                            docs = output.get("documents", [])
                            if docs:
                                kb_accumulated_docs.extend(docs)
    
    return SubgraphEventResult(
        results=results,
        kb_accumulated_docs=kb_accumulated_docs,
    )

