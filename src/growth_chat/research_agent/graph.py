"""
LangGraph workflow for Research Agent.

Implements a ReAct agent with specialized tools for querying DAO data sources,
with a hard limit on tool calls to prevent runaway loops.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import (AIMessage, BaseMessage, HumanMessage,
                                     SystemMessage, ToolMessage)
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from src.utils.checkpointer import get_checkpointer
from src.utils.logger import logger
from src.utils.model_factory import create_chat_model, extract_text_content

from ..prompts import MULTI_STEP_PLANS_PROMPT
from ..schemas import AttachedFile
from ..shared_tools import create_blockchain_tools
from .prompts import RESEARCH_AGENT_SYSTEM_PROMPT, USER_CONTEXT_TEMPLATE
from .tools import create_research_tools

# Create shared checkpointer at module level
_SHARED_CHECKPOINTER = get_checkpointer()

# Maximum tool calls before forcing an answer
MAX_TOOL_CALLS = int(os.getenv("RESEARCH_AGENT_MAX_TOOLS", "6"))


def add_messages(left: Sequence[BaseMessage], right: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    """Merge message sequences."""
    return list(left) + list(right)


def merge_attached_files(left: List[AttachedFile], right: List[AttachedFile]) -> List[AttachedFile]:
    """Keep the latest attached files (from parent state or updates)."""
    # If right has files, use them; otherwise keep left
    return right if right else left


# Pattern to match chart-preview blocks with base64 data
# Matches: ```chart-preview\n{...}\n```
CHART_PREVIEW_PATTERN = re.compile(
    r'```chart-preview\s*\n\{[^}]*"data"\s*:\s*"[^"]*"[^}]*\}\s*\n```',
    re.DOTALL
)


def strip_chart_previews_from_content(content: str) -> str:
    """Strip chart-preview blocks from message content to reduce token usage.
    
    Chart previews contain base64-encoded PNG/SVG data that can be 100k+ tokens.
    These are kept in the original tool output for streaming to the user,
    but stripped before sending to the model on subsequent calls.
    
    Args:
        content: The message content string
        
    Returns:
        Content with chart-preview blocks replaced with a placeholder
    """
    if not content or "```chart-preview" not in content:
        return content
    
    # Replace chart-preview blocks with a placeholder
    replaced = CHART_PREVIEW_PATTERN.sub(
        "[Chart was generated and displayed to user]",
        content
    )
    
    if replaced != content:
        logger.debug("[ResearchAgent] Stripped chart-preview blocks from message")
    
    return replaced


def strip_chart_previews_from_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Strip chart-preview blocks from ToolMessages to reduce token usage.
    
    Creates new ToolMessage instances with stripped content to avoid
    mutating the original messages in state.
    
    Args:
        messages: List of messages to process
        
    Returns:
        New list with ToolMessages having chart previews stripped
    """
    processed = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, str):
                stripped_content = strip_chart_previews_from_content(content)
                if stripped_content != content:
                    # Create a new ToolMessage with stripped content
                    processed.append(ToolMessage(
                        content=stripped_content,
                        tool_call_id=msg.tool_call_id,
                        name=getattr(msg, 'name', None),
                    ))
                    continue
        processed.append(msg)
    return processed


class ResearchAgentState(BaseModel):
    """State for the research agent with tool call tracking."""
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)
    tool_call_count: int = Field(default=0)
    # Attached files from parent state (for code_execute tool)
    attached_files: Annotated[List[AttachedFile], merge_attached_files] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


def create_research_agent_graph(
    user_id: Optional[str] = None,
    org_slug: Optional[str] = None,
    auth_token: str = "",
):
    """
    Create and compile the LangGraph workflow for the Research Agent.
    
    Features:
    - ReAct agent with specialized data source tools
    - Hard limit on tool calls to prevent runaway loops
    - Forces answer after MAX_TOOL_CALLS reached
    - Organization blockchain proposals tool (if configured)
    
    Args:
        user_id: Optional user ID for context
        org_slug: Optional organization slug for context
        auth_token: Privy authentication token for blockchain tools
    
    Returns:
        Compiled graph with shared checkpointer
    """
    tools = create_research_tools()
    
    # Add organization blockchain tools if auth context is available
    if auth_token and org_slug:
        blockchain_tools = create_blockchain_tools(auth_token=auth_token, org_slug=org_slug)
        tools.extend(blockchain_tools)
        logger.info(f"[ResearchAgent] Added {len(blockchain_tools)} org blockchain tools")
    
    logger.info(f"[ResearchAgent] Creating graph with {len(tools)} tools, max_calls={MAX_TOOL_CALLS}")
    
    # Calculate dynamic dates for the prompt
    today = datetime.now()
    prompt_context = {
        "current_date": today.strftime("%Y-%m-%d"),
        "one_week_ago": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
        "one_month_ago": (today - timedelta(days=30)).strftime("%Y-%m-%d"),
        "three_months_ago": (today - timedelta(days=90)).strftime("%Y-%m-%d"),
        "six_months_ago": (today - timedelta(days=180)).strftime("%Y-%m-%d"),
        "year_start": f"{today.year}-01-01",
        "multi_step_plans": MULTI_STEP_PLANS_PROMPT,
    }
    
    # Build system prompt with date context and multi-step plans
    system_prompt = RESEARCH_AGENT_SYSTEM_PROMPT.format(**prompt_context)
    
    user_context = ""
    if user_id or org_slug:
        user_context = USER_CONTEXT_TEMPLATE.format(
            user_id=user_id or "Unknown",
            org_slug=org_slug or "Unknown",
        )
    
    full_prompt = system_prompt
    if user_context:
        full_prompt = f"{system_prompt}\n\n{user_context}"
    
    # Create model with tools
    model_name = os.getenv("RESEARCH_AGENT_MODEL", "gemini-3-flash-preview")
    logger.info(f"[ResearchAgent] Using model: {model_name}")
    
    model = create_chat_model(
        model_name=model_name,
        temperature=float(os.getenv("RESEARCH_AGENT_TEMPERATURE", "0.3"))
    )
    model_with_tools = model.bind_tools(tools)
    
    # Create tool node with custom executor that passes attached_files
    base_tool_node = ToolNode(tools)
    
    async def call_model(state: ResearchAgentState) -> Dict[str, Any]:
        """Call the model, potentially forcing an answer if at tool limit."""
        messages = list(state.messages)
        tool_count = state.tool_call_count
        
        # Strip chart-preview blocks from ToolMessages to reduce token usage
        # These contain base64 PNG data that can be 100k+ tokens
        messages = strip_chart_previews_from_messages(messages)
        
        # Add system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=full_prompt)] + messages
        
        # Check if we're at the limit - force answer
        if tool_count >= MAX_TOOL_CALLS:
            logger.warning(f"[ResearchAgent] Tool limit reached ({tool_count}/{MAX_TOOL_CALLS}), forcing answer")
            
            # Add instruction to stop and answer
            force_answer_msg = HumanMessage(
                content="STOP. You have reached the maximum number of tool calls. "
                        "Synthesize all the information you have gathered and provide your final answer NOW. "
                        "Do NOT call any more tools."
            )
            messages = messages + [force_answer_msg]
            
            # Call model without tools to force text response
            response = await model.ainvoke(messages)
        else:
            # Normal call with tools available
            response = await model_with_tools.ainvoke(messages)
        
        return {"messages": [response]}
    
    async def run_tools(state: ResearchAgentState) -> Dict[str, Any]:
        """Execute tools and increment counter."""
        # Count how many tool calls are being made
        last_message = state.messages[-1]
        num_calls = len(last_message.tool_calls) if hasattr(last_message, 'tool_calls') and last_message.tool_calls else 0
        
        # Update code_execute tool with attached_files from state
        # This allows the tool to access files uploaded by the user
        attached_files = state.attached_files if hasattr(state, 'attached_files') else []
        for tool in tools:
            if hasattr(tool, 'name') and tool.name == 'code_execute':
                tool.set_attached_files(attached_files)
                logger.info(f"[ResearchAgent] Injected {len(attached_files)} attached files into code_execute tool")
        
        # Run the tools
        result = await base_tool_node.ainvoke(state)
        
        # Increment counter
        new_count = state.tool_call_count + num_calls
        logger.info(f"[ResearchAgent] Tool calls: {state.tool_call_count} -> {new_count}")
        
        return {
            "messages": result.get("messages", []),
            "tool_call_count": new_count
        }
    
    def should_continue(state: ResearchAgentState) -> str:
        """Determine if we should continue to tools or end."""
        last_message = state.messages[-1]
        
        # If no tool calls, we're done
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            return END
        
        # Count how many tool calls the LLM wants to make
        pending_calls = len(last_message.tool_calls) if last_message.tool_calls else 0
        
        # If already at limit, don't run more tools
        if state.tool_call_count >= MAX_TOOL_CALLS:
            logger.warning(f"[ResearchAgent] At tool limit ({state.tool_call_count}/{MAX_TOOL_CALLS}), ending")
            return END
        
        # If running these tools would exceed limit, still run them but log warning
        if state.tool_call_count + pending_calls > MAX_TOOL_CALLS:
            logger.warning(f"[ResearchAgent] Tool calls ({state.tool_call_count}+{pending_calls}) will exceed limit, running anyway")
        
        return "tools"
    
    # Build graph
    graph = StateGraph(ResearchAgentState)
    
    graph.add_node("model", call_model)
    graph.add_node("tools", run_tools)
    
    graph.set_entry_point("model")
    
    graph.add_conditional_edges(
        "model",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    
    graph.add_edge("tools", "model")
    
    logger.info("[ResearchAgent] Graph created successfully")
    return graph.compile(checkpointer=_SHARED_CHECKPOINTER)
