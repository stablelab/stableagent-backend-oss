"""
LangGraph workflow for Onboarding Agent.

Implements a ReAct agent with onboarding-specific prompts and tools.
Combines app automation tools with onboarding progress tracking.
"""
import os
from typing import Dict, List, Optional, Any

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.graph import MessagesState, StateGraph

from src.utils.checkpointer import get_checkpointer
from src.utils.model_factory import create_chat_model

from ..schemas import UserInfo
from .prompts import get_onboarding_prompt, get_greeting_message
from .tools.onboarding_tools import create_onboarding_tools

# Create shared checkpointer at module level (persists across requests)
_SHARED_CHECKPOINTER = get_checkpointer()


def create_onboarding_agent_node(
    tools: List[BaseTool],
    user_info: Optional[UserInfo] = None,
    onboarding_status: Optional[Dict[str, Any]] = None,
    flow_type: str = "admin_setup",
):
    """
    Create the agent node for the Onboarding Agent.
    
    Args:
        tools: List of tools available to the agent
        user_info: User information (id, handle, email, org context)
        onboarding_status: Current onboarding progress
        flow_type: Type of onboarding flow ('admin_setup' or 'user_joining')
    
    Returns:
        Agent node for the graph
    """
    # Build user context dict
    user_context = {
        "user_id": user_info.get("id", "Unknown") if user_info else "Unknown",
        "user_handle": user_info.get("handle", "Unknown") if user_info else "Unknown",
        "user_email": user_info.get("email", "Unknown") if user_info else "Unknown",
        "org_id": user_info.get("org_id", "None") if user_info else "None",
        "org_slug": user_info.get("org_slug", "None") if user_info else "None",
        "org_name": user_info.get("org_name", "Unknown Organization") if user_info else "Unknown Organization",
        "user_role": user_info.get("role", "Builder") if user_info else "Builder",
    }
    
    # Default onboarding status if not provided
    if onboarding_status is None:
        onboarding_status = {
            "flow_type": flow_type,
            "current_step": "welcome",
            "completed_steps": [],
            "steps_remaining": 11 if flow_type == "admin_setup" else 7,
            "percent_complete": 0,
            "is_complete": False,
        }
    
    # Generate the system prompt with all context
    system_prompt = get_onboarding_prompt(
        flow_type=flow_type,
        user_context=user_context,
        onboarding_status=onboarding_status,
    )
    
    agent = create_agent(
        model=create_chat_model(
            model_name=os.getenv("ONBOARDING_MODEL", os.getenv("APP_AUTOMATION_MODEL", "gemini-3-flash-preview")),
            temperature=float(os.getenv("ONBOARDING_TEMPERATURE", os.getenv("APP_AUTOMATION_TEMPERATURE", "0.3")))
        ),
        system_prompt=system_prompt,
        tools=tools,
    )
    
    return agent


def create_onboarding_graph(
    auth_token: str,
    org_id: int,
    org_slug: str,
    user_info: Optional[UserInfo] = None,
    onboarding_status: Optional[Dict[str, Any]] = None,
    flow_type: str = "admin_setup",
):
    """
    Create and compile the LangGraph workflow for the Onboarding Agent.
    
    Uses a ReAct agent with specialized onboarding prompts and all available tools
    (app automation + onboarding-specific tools).
    
    Args:
        auth_token: Authentication token for API calls
        org_id: Organization ID
        org_slug: Organization slug
        user_info: User information (id, handle, email, display_name, is_global_admin, org context)
        onboarding_status: Current onboarding progress (from API)
        flow_type: Type of onboarding flow ('admin_setup' or 'user_joining')
    
    Returns:
        Compiled graph with shared checkpointer
    """
    # Check if user is a global admin (for org management tools)
    is_global_admin = user_info.get("is_global_admin", False) if user_info else False
    
    # Create all tools (app automation + onboarding)
    tools = create_onboarding_tools(auth_token, org_id=org_id, org_slug=org_slug, is_global_admin=is_global_admin)
    
    # Create agent node with onboarding context
    onboarding_agent = create_onboarding_agent_node(
        tools=tools,
        user_info=user_info,
        onboarding_status=onboarding_status,
        flow_type=flow_type,
    )
    
    # Build the graph
    graph = StateGraph(MessagesState)
    graph.add_node("agent", onboarding_agent)
    graph.set_entry_point("agent")
    graph.set_finish_point("agent")
    
    return graph.compile(checkpointer=_SHARED_CHECKPOINTER)


def get_initial_greeting(
    flow_type: str,
    onboarding_status: Optional[Dict[str, Any]] = None,
    org_name: str = "the organization",
) -> str:
    """
    Get the initial greeting message for the onboarding flow.
    
    This can be used to show a greeting before the user sends any message,
    giving them context about where they are in onboarding.
    
    Args:
        flow_type: Type of onboarding flow ('admin_setup' or 'user_joining')
        onboarding_status: Current onboarding progress
        org_name: Name of the organization
        
    Returns:
        Greeting message string
    """
    if onboarding_status is None:
        onboarding_status = {
            "is_complete": False,
            "current_step": "welcome",
            "completed_steps": [],
            "percent_complete": 0,
        }
    
    return get_greeting_message(flow_type, onboarding_status, org_name)

