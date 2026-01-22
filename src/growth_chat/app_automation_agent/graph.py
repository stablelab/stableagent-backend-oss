"""
LangGraph workflow for App Automation Agent.

Implements a simple ReAct agent with tool calling and approval flow for mutating operations.
Supports both team management and form management tools.
"""
import os
from typing import List, Optional

from langchain.agents import create_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool
from langgraph.graph import MessagesState, StateGraph

from src.utils.checkpointer import get_checkpointer
from src.utils.model_factory import create_chat_model

from ..prompts import MULTI_STEP_PLANS_PROMPT
from ..schemas import UserInfo
from .prompts import AGENT_SYSTEM_PROMPT_TEMPLATE, USER_CONTEXT_TEMPLATE
from .tools.tools import create_all_tools

# Create shared checkpointer at module level (persists across requests)
_SHARED_CHECKPOINTER = get_checkpointer()

# Agent Node

def create_agent_node(tools: List[BaseTool], user_info: Optional[UserInfo] = None):
    """Agent node for the App Automation Agent. Will be a subgraph of the main parent graph."""
    # Build user context if user info is available
    user_context = ""
    if user_info:
        user_context = USER_CONTEXT_TEMPLATE.format(
            user_id=user_info.get('id', 'Unknown'),
            handle=user_info.get('handle', 'Unknown'),
            email=user_info.get('email', 'Unknown'),
            display_name=user_info.get('display_name', 'Unknown'),
            org_slug=user_info.get('org_slug', 'Unknown'),
        )
    
    system_prompt = AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        user_context=user_context,
        multi_step_plans=MULTI_STEP_PLANS_PROMPT,
    )
    
    agent = create_agent(
        model=create_chat_model(model_name=os.getenv("APP_AUTOMATION_MODEL", "gemini-3-flash-preview"), temperature=os.getenv("APP_AUTOMATION_TEMPERATURE", "0.3")),
        system_prompt=system_prompt,
        tools=tools,
    )
    return agent


# Graph Construction

def create_app_automation_graph(
    auth_token: str,
    org_id: int,
    org_slug: str,
    user_info: Optional[UserInfo] = None,
):
    """
    Create and compile the LangGraph workflow for the App Automation Agent.
    
    Uses a simple ReAct agent with tool approval for mutating operations.
    Includes both team management and form management tools.
    
    Args:
        auth_token: Authentication token for API calls
        org_id: Organization ID
        org_slug: Organization slug
        user_info: User information (id, handle, email, display_name, is_global_admin)
    
    Returns:
        Compiled graph with shared checkpointer
    """
    # Check if user is a global admin (for org management tools)
    is_global_admin = user_info.get("is_global_admin", False) if user_info else False
    
    # Create graph with all tools (teams + forms)
    automation_agent = create_agent_node(
        tools=create_all_tools(
            auth_token, 
            org_id=org_id, 
            org_slug=org_slug, 
            is_global_admin=is_global_admin
        ),
        user_info=user_info,
    )
    graph = StateGraph(MessagesState)
    graph.add_node("agent", automation_agent)
    graph.set_entry_point("agent")
    graph.set_finish_point("agent")
    return graph.compile(checkpointer=_SHARED_CHECKPOINTER)
